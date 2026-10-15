"""In-memory stand-ins for the ports, and builders for test data."""
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from assessments.application.acl import ExternalRegistriesService
from assessments.application.outbound_services import (
    AuctionEvaluationService,
    CreditBureau,
    EvaluationOutcome,
    InvestmentUnavailableError,
)
from assessments.application.services import RiskAssessmentApplicationService
from assessments.domain.entities import RiskAssessment
from assessments.domain.repositories import RiskAssessmentRepository
from assessments.domain.services import PointsGradingPolicy
from assessments.domain.value_objects import (
    AuctionFacts,
    AuctionId,
    CreditReport,
    Currency,
    DeliveryStatus,
    GradingDecision,
    Money,
    Payer,
    RiskGrade,
    Ruc,
    ScoreFactor,
)
from registries.interfaces.acl import PayerStandingRecord
from shared.application.events import EventBus
from shared.application.messaging import Inbox

NOW = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)


class InMemoryRiskAssessmentRepository(RiskAssessmentRepository):
    """Keeps assessments in a dict, assigning ids like the database would."""

    def __init__(self) -> None:
        self.rows: dict[int, RiskAssessment] = {}
        self._next_id = 1

    async def save(self, risk_assessment: RiskAssessment) -> RiskAssessment:
        if risk_assessment.id is None:
            stored = RiskAssessment(
                risk_assessment.assessment_id,
                risk_assessment.facts,
                risk_assessment.decision,
                risk_assessment.assessed_at,
                risk_assessment.source_event_id,
                delivery_status=risk_assessment.delivery_status,
                delivery_attempts=risk_assessment.delivery_attempts,
                next_delivery_at=risk_assessment.next_delivery_at,
                last_delivery_error=risk_assessment.last_delivery_error,
                delivered_at=risk_assessment.delivered_at,
                investment_auction_status=risk_assessment.investment_auction_status,
                id=self._next_id,
            )
            self._next_id += 1
        else:
            stored = risk_assessment
        assert stored.id is not None
        self.rows[stored.id] = stored
        return stored

    async def find_by_auction_id(self, auction_id: AuctionId) -> RiskAssessment | None:
        return next((row for row in self.rows.values() if row.facts.auction_id == auction_id), None)

    async def find_due_for_delivery(self, now: datetime, limit: int) -> list[RiskAssessment]:
        due = [
            row
            for row in self.rows.values()
            if row.delivery_status is DeliveryStatus.PENDING
            and row.next_delivery_at is not None
            and row.next_delivery_at <= now
        ]
        return sorted(due, key=lambda row: (row.next_delivery_at or now, row.id or 0))[:limit]


class InMemoryInbox(Inbox):
    """Remembers processed events; only committed ones survive a rollback in real life."""

    def __init__(self) -> None:
        self.events: dict[str, tuple[str, str]] = {}

    async def has_processed(self, event_id: str) -> bool:
        return event_id in self.events

    async def record(self, event_id: str, event_type: str, aggregate_id: str) -> None:
        self.events[event_id] = (event_type, aggregate_id)


class FakeUnitOfWork:
    """Counts commits and rollbacks."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class StubEvaluationService(AuctionEvaluationService):
    """Answers each delivery with the next scripted outcome, or raises it."""

    outcomes: list[EvaluationOutcome | InvestmentUnavailableError] = field(default_factory=list)
    calls: list[dict[str, object]] = field(default_factory=list)

    async def submit(
        self,
        *,
        auction_id: str,
        assessment_id: str,
        risk_grade: str,
        full_balance_outstanding: bool,
        assessed_at: datetime,
    ) -> EvaluationOutcome:
        return self._answer(
            {
                "kind": "evaluation",
                "auction_id": auction_id,
                "assessment_id": assessment_id,
                "risk_grade": risk_grade,
                "full_balance_outstanding": full_balance_outstanding,
                "assessed_at": assessed_at,
            }
        )

    async def reject(
        self,
        *,
        auction_id: str,
        assessment_id: str,
        reason_code: str,
        reason: str,
        assessed_at: datetime,
    ) -> EvaluationOutcome:
        return self._answer(
            {
                "kind": "rejection",
                "auction_id": auction_id,
                "assessment_id": assessment_id,
                "reason_code": reason_code,
                "reason": reason,
                "assessed_at": assessed_at,
            }
        )

    def _answer(self, call: dict[str, object]) -> EvaluationOutcome:
        self.calls.append(call)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, InvestmentUnavailableError):
            raise outcome
        return outcome


ACTIVE_COMPANY = PayerStandingRecord(
    registry_loaded=True,
    found=True,
    name="PAGADOR SOCIEDAD ANONIMA CERRADA",
    status="ACTIVO",
    domicile_condition="HABIDO",
    ubigeo="150101",
)


class FakeRegistriesFacade:
    """Answers every payer with the same standing; stands in for the Registries facade."""

    def __init__(self, standing: PayerStandingRecord = ACTIVE_COMPANY) -> None:
        self.standing = standing
        self.asked: list[str] = []

    async def payer_standing(self, ruc: str) -> PayerStandingRecord:
        self.asked.append(ruc)
        return self.standing


class FixedCreditBureau(CreditBureau):
    """Reports the same thing for every payer; nothing by default."""

    def __init__(self, report: CreditReport | None = None) -> None:
        self.fixed = report
        self.asked: list[str] = []

    async def report(self, ruc: Ruc) -> CreditReport | None:
        self.asked.append(ruc.value)
        return self.fixed


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@dataclass
class ServiceUnderTest:
    """The application service wired to fakes, with the fakes at hand."""

    service: RiskAssessmentApplicationService
    repository: InMemoryRiskAssessmentRepository
    inbox: InMemoryInbox
    unit_of_work: FakeUnitOfWork
    evaluations: StubEvaluationService
    registries: FakeRegistriesFacade
    credit_bureau: FixedCreditBureau
    event_bus: EventBus
    clock: Clock


def build_service(
    evaluations: StubEvaluationService | None = None,
    standing: PayerStandingRecord = ACTIVE_COMPANY,
    credit: CreditReport | None = None,
) -> ServiceUnderTest:
    """Wire the application service to fresh fakes and the points policy."""
    repository = InMemoryRiskAssessmentRepository()
    inbox = InMemoryInbox()
    unit_of_work = FakeUnitOfWork()
    stub = evaluations or StubEvaluationService()
    registries = FakeRegistriesFacade(standing)
    credit_bureau = FixedCreditBureau(credit)
    bus = EventBus()
    clock = Clock()
    service = RiskAssessmentApplicationService(
        repository,
        inbox,
        ExternalRegistriesService(cast(Any, registries)),
        credit_bureau,
        stub,
        PointsGradingPolicy(),
        unit_of_work,
        bus,
        clock,
    )
    return ServiceUnderTest(service, repository, inbox, unit_of_work, stub, registries, credit_bureau, bus, clock)


def graded(grade: RiskGrade = RiskGrade.B) -> GradingDecision:
    """An eligible decision with one factor."""
    return GradingDecision(
        eligible=True,
        grade=grade,
        score=60,
        factors=(ScoreFactor("DOMICILE_FOUND", 10, "Domicilio fiscal HABIDO en SUNAT."),),
        full_balance_outstanding=True,
        policy_version="points-v2",
    )


def auction_created(**overrides: Any) -> dict[str, Any]:
    """Keyword arguments for ``assess_auction``, valid unless overridden."""
    arguments: dict[str, Any] = {
        "event_id": "10000000-0000-4000-8000-000000000001",
        "auction_id": "20000000-0000-4000-8000-000000000001",
        "invoice_id": "30000000-0000-4000-8000-000000000001",
        "mype_id": "40000000-0000-4000-8000-000000000001",
        "payer_ruc": "20123456789",
        "payer_name": "Pagador S.A.",
        "due_date": date(2026, 12, 31),
        "invoice_amount": Decimal("10000.00"),
        "currency": "PEN",
        "green_certified": False,
    }
    arguments.update(overrides)
    return arguments


def facts(auction_id: str = "20000000-0000-4000-8000-000000000001") -> AuctionFacts:
    """Valid auction facts."""
    return AuctionFacts(
        auction_id=AuctionId(auction_id),
        invoice_id="30000000-0000-4000-8000-000000000001",
        mype_id="40000000-0000-4000-8000-000000000001",
        payer=Payer(Ruc("20123456789"), "Pagador S.A."),
        due_date=date(2026, 12, 31),
        invoice_amount=Money(Decimal("10000"), Currency.PEN),
        green_certified=False,
    )
