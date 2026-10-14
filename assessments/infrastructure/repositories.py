"""SQLAlchemy implementation of the Assessments repository port.

The repository is the only place that knows both the aggregate and its table:
it maps one to the other in both directions, so neither has to know about the
other.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assessments.domain.entities import RiskAssessment
from assessments.domain.repositories import RiskAssessmentRepository
from assessments.domain.value_objects import (
    AssessmentId,
    AuctionFacts,
    AuctionId,
    Currency,
    DeliveryStatus,
    GradingDecision,
    Money,
    Payer,
    RiskGrade,
    Ruc,
)
from assessments.infrastructure.models import RiskAssessmentModel


class SqlAlchemyRiskAssessmentRepository(RiskAssessmentRepository):
    """Stores :class:`RiskAssessment` aggregates in the ``risk_assessments`` table."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository on the unit of work's session.

        Args:
            session (AsyncSession): The session of the current unit of work.
        """
        self._session = session

    async def save(self, risk_assessment: RiskAssessment) -> RiskAssessment:
        model = await self._session.merge(self._to_model(risk_assessment))
        await self._session.flush()
        return self._to_entity(model)

    async def find_by_auction_id(self, auction_id: AuctionId) -> RiskAssessment | None:
        model = await self._session.scalar(
            select(RiskAssessmentModel).where(RiskAssessmentModel.auction_id == auction_id.value)
        )
        return self._to_entity(model) if model else None

    async def find_due_for_delivery(self, now: datetime, limit: int) -> list[RiskAssessment]:
        models = await self._session.scalars(
            select(RiskAssessmentModel)
            .where(
                RiskAssessmentModel.delivery_status == DeliveryStatus.PENDING.value,
                RiskAssessmentModel.next_delivery_at <= now,
            )
            .order_by(RiskAssessmentModel.next_delivery_at, RiskAssessmentModel.id)
            .limit(limit)
        )
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(assessment: RiskAssessment) -> RiskAssessmentModel:
        facts = assessment.facts
        decision = assessment.decision
        return RiskAssessmentModel(
            id=assessment.id,
            assessment_id=assessment.assessment_id.value,
            auction_id=facts.auction_id.value,
            invoice_id=facts.invoice_id,
            mype_id=facts.mype_id,
            payer_ruc=facts.payer.ruc.value,
            payer_name=facts.payer.name,
            due_date=facts.due_date,
            invoice_amount=facts.invoice_amount.amount,
            invoice_currency=facts.invoice_amount.currency.value,
            green_certified=facts.green_certified,
            risk_grade=decision.grade.value,
            full_balance_outstanding=decision.full_balance_outstanding,
            grading_policy=decision.policy_version,
            provisional=decision.provisional,
            assessed_at=assessment.assessed_at,
            source_event_id=assessment.source_event_id,
            delivery_status=assessment.delivery_status.value,
            delivery_attempts=assessment.delivery_attempts,
            next_delivery_at=assessment.next_delivery_at,
            last_delivery_error=assessment.last_delivery_error,
            delivered_at=assessment.delivered_at,
            investment_auction_status=assessment.investment_auction_status,
        )

    @staticmethod
    def _to_entity(model: RiskAssessmentModel) -> RiskAssessment:
        return RiskAssessment(
            AssessmentId(model.assessment_id),
            AuctionFacts(
                auction_id=AuctionId(model.auction_id),
                invoice_id=model.invoice_id,
                mype_id=model.mype_id,
                payer=Payer(Ruc(model.payer_ruc), model.payer_name),
                due_date=model.due_date,
                invoice_amount=Money(model.invoice_amount, Currency(model.invoice_currency)),
                green_certified=model.green_certified,
            ),
            GradingDecision(
                grade=RiskGrade(model.risk_grade),
                full_balance_outstanding=model.full_balance_outstanding,
                policy_version=model.grading_policy,
                provisional=model.provisional,
            ),
            model.assessed_at,
            model.source_event_id,
            delivery_status=DeliveryStatus(model.delivery_status),
            delivery_attempts=model.delivery_attempts,
            next_delivery_at=model.next_delivery_at,
            last_delivery_error=model.last_delivery_error,
            delivered_at=model.delivered_at,
            investment_auction_status=model.investment_auction_status,
            id=model.id,
        )
