"""The points policy: the filter, each signal, the bands, and the names."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from assessments.domain.services import (
    PAYER_DOMICILE_NOT_FOUND,
    PAYER_NOT_ACTIVE,
    PAYER_NOT_IN_REGISTRY,
    PAYER_SHELL_COMPANY,
    POINTS_POLICY_VERSION,
    PointsGradingPolicy,
    grade_for,
    names_match,
    normalize_company_name,
)
from assessments.domain.value_objects import (
    AuctionFacts,
    AuctionId,
    CreditReport,
    Currency,
    Money,
    Payer,
    PayerStanding,
    RiskGrade,
    Ruc,
    SanctionPeriod,
    SbsRating,
)

TODAY = date(2026, 10, 14)
ACTIVE_COMPANY = PayerStanding(
    registry_loaded=True,
    found=True,
    name="PAGADOR SOCIEDAD ANONIMA CERRADA",
    status="ACTIVO",
    domicile_condition="HABIDO",
    ubigeo="150101",
)


def auction(ruc: str = "20123456789", name: str = "Pagador S.A.C.", days: int = 45) -> AuctionFacts:
    return AuctionFacts(
        auction_id=AuctionId("auction-1"),
        invoice_id="invoice-1",
        mype_id="mype-1",
        payer=Payer(Ruc(ruc), name),
        due_date=TODAY + timedelta(days=days),
        invoice_amount=Money(Decimal("10000"), Currency.PEN),
        green_certified=False,
    )


def standing(**changes: Any) -> PayerStanding:
    values: dict[str, Any] = {
        "registry_loaded": ACTIVE_COMPANY.registry_loaded,
        "found": ACTIVE_COMPANY.found,
        "name": ACTIVE_COMPANY.name,
        "status": ACTIVE_COMPANY.status,
        "domicile_condition": ACTIVE_COMPANY.domicile_condition,
        "ubigeo": ACTIVE_COMPANY.ubigeo,
        "withholding_agent": False,
        "perception_agent": False,
    }
    values.update(changes)
    return PayerStanding(**values)


def codes(facts: AuctionFacts, payer: PayerStanding) -> dict[str, int]:
    decision = PointsGradingPolicy().grade(facts, payer, None, TODAY)
    return {factor.code: factor.points for factor in decision.factors}


def test_a_typical_company_is_b() -> None:
    decision = PointsGradingPolicy().grade(auction(), ACTIVE_COMPANY, None, TODAY)
    assert decision.eligible is True
    assert decision.score == 65
    assert decision.grade is RiskGrade.B
    assert decision.policy_version == POINTS_POLICY_VERSION
    assert decision.provisional is False
    assert {factor.code for factor in decision.factors} == {
        "DOMICILE_FOUND",
        "COMPANY",
        "NAME_MATCHES",
        "TERM_31_TO_60_DAYS",
    }


def test_a_withholding_agent_is_a() -> None:
    decision = PointsGradingPolicy().grade(auction(), standing(withholding_agent=True), None, TODAY)
    assert decision.score == 85
    assert decision.grade is RiskGrade.A


def test_a_perception_agent_counts_less_and_never_on_top_of_withholding() -> None:
    assert codes(auction(), standing(perception_agent=True))["PERCEPTION_AGENT"] == 10
    both = codes(auction(), standing(withholding_agent=True, perception_agent=True))
    assert both["WITHHOLDING_AGENT"] == 20
    assert "PERCEPTION_AGENT" not in both


def test_a_name_that_does_not_match_lowers_it_to_c() -> None:
    decision = PointsGradingPolicy().grade(auction(name="Otra Empresa S.A."), ACTIVE_COMPANY, None, TODAY)
    assert decision.score == 45
    assert decision.grade is RiskGrade.C
    assert "NAME_MISMATCH" in {factor.code for factor in decision.factors}


@pytest.mark.parametrize(
    ("days", "code", "points"),
    [(10, "TERM_UP_TO_30_DAYS", 10), (30, "TERM_UP_TO_30_DAYS", 10), (31, "TERM_31_TO_60_DAYS", 5),
     (60, "TERM_31_TO_60_DAYS", 5), (90, "TERM_61_TO_90_DAYS", 0), (91, "TERM_OVER_90_DAYS", -10)],
)
def test_the_term_counts_days_to_the_due_date(days: int, code: str, points: int) -> None:
    assert codes(auction(days=days), ACTIVE_COMPANY)[code] == points


def test_individuals_and_unverified_addresses_count_against() -> None:
    factors = codes(auction(ruc="10456789012"), standing(domicile_condition="PENDIENTE"))
    assert factors["INDIVIDUAL"] == -5
    assert factors["DOMICILE_UNVERIFIED"] == -10


@pytest.mark.parametrize(
    ("payer", "code"),
    [
        (standing(found=False, name=None, status=None, domicile_condition=None), PAYER_NOT_IN_REGISTRY),
        (standing(status="BAJA DE OFICIO"), PAYER_NOT_ACTIVE),
        (standing(status="SUSPENSION TEMPORAL"), PAYER_NOT_ACTIVE),
        (standing(domicile_condition="NO HABIDO"), PAYER_DOMICILE_NOT_FOUND),
        (standing(domicile_condition="NO HALLADO SE MUDO D"), PAYER_DOMICILE_NOT_FOUND),
        (standing(shell_company=True), PAYER_SHELL_COMPANY),
    ],
)
def test_the_filter_rejects_with_a_code_and_a_reason(payer: PayerStanding, code: str) -> None:
    decision = PointsGradingPolicy().grade(auction(), payer, None, TODAY)
    assert decision.eligible is False
    assert decision.grade is None
    assert decision.rejection_code == code
    assert decision.rejection_reason


def test_without_the_registry_every_auction_is_c_and_never_rejected() -> None:
    decision = PointsGradingPolicy().grade(auction(), PayerStanding(registry_loaded=False, found=False), None, TODAY)
    assert decision.eligible is True
    assert decision.grade is RiskGrade.C
    assert decision.score is None
    assert [factor.code for factor in decision.factors] == ["REGISTRY_UNAVAILABLE"]


@pytest.mark.parametrize(("score", "grade"), [(100, RiskGrade.A), (75, RiskGrade.A), (74, RiskGrade.B),
                                              (55, RiskGrade.B), (54, RiskGrade.C), (0, RiskGrade.C)])
def test_bands(score: int, grade: RiskGrade) -> None:
    assert grade_for(score) is grade


@pytest.mark.parametrize(
    ("invoice", "registered"),
    [
        ("Pagador S.A.C.", "PAGADOR SOCIEDAD ANONIMA CERRADA"),
        ("Distribuidora Peñaflor E.I.R.L.", "DISTRIBUIDORA PEÑAFLOR EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA"),
        ("Constructora Lima SAC", "CONSTRUCTORA LIMA S.A.C."),
        ("Agroexport del Norte S.A.", "AGROEXPORT DEL NORTE S A"),
    ],
)
def test_the_same_company_written_differently_matches(invoice: str, registered: str) -> None:
    assert names_match(invoice, registered)


def test_different_companies_do_not_match() -> None:
    assert not names_match("Textil Andes S.A.C.", "MINERA AURORA S.A.")
    assert not names_match("S.A.C.", "S.A.")


def test_normalization_removes_accents_punctuation_and_legal_forms() -> None:
    assert normalize_company_name("Exportadora  Señor de Sipán, S.R.L.") == "EXPORTADORA SENOR DE SIPAN"


def test_debt_in_coactive_collection_lowers_the_grade() -> None:
    decision = PointsGradingPolicy().grade(auction(), standing(coactive_debt=Decimal("125000.50")), None, TODAY)
    factor = next(f for f in decision.factors if f.code == "COACTIVE_DEBT")
    assert factor.points == -20
    assert "125,000.50" in factor.detail
    assert decision.score == 45
    assert decision.grade is RiskGrade.C


@pytest.mark.parametrize(
    ("period", "in_force"),
    [
        (SanctionPeriod(date(2026, 1, 1), date(2027, 1, 1)), True),
        (SanctionPeriod(date(2026, 1, 1), None), True),
        (SanctionPeriod(date(2025, 1, 1), date(2026, 10, 13)), False),
        (SanctionPeriod(date(2026, 11, 1), date(2027, 11, 1)), False),
        (SanctionPeriod(date(2026, 1, 1), TODAY), True),
    ],
)
def test_only_an_oece_disqualification_in_force_counts(period: SanctionPeriod, in_force: bool) -> None:
    factors = codes(auction(), standing(oece_disqualifications=(period,)))
    assert ("OECE_DISQUALIFIED" in factors) is in_force


def test_unpaid_oece_fines_and_environmental_offences_count_against() -> None:
    fines = (SanctionPeriod(date(2023, 1, 3), date(2023, 5, 3), Decimal("2300")),)
    factors = codes(auction(), standing(oece_fines=fines, environmental_infractions=3))
    assert factors["OECE_UNPAID_FINE"] == -10
    assert factors["ENVIRONMENTAL_OFFENDER"] == -5


@pytest.mark.parametrize(
    ("rating", "code", "points"),
    [
        (SbsRating.NORMAL, "CREDIT_RATING_NORMAL", 0),
        (SbsRating.POTENTIAL_PROBLEMS, "CREDIT_RATING_CPP", -10),
        (SbsRating.DEFICIENT, "CREDIT_RATING_DEFICIENT", -20),
        (SbsRating.DOUBTFUL, "CREDIT_RATING_DOUBTFUL", -30),
        (SbsRating.LOSS, "CREDIT_RATING_LOSS", -40),
    ],
)
def test_the_credit_rating_only_ever_takes_points(rating: SbsRating, code: str, points: int) -> None:
    report = CreditReport(rating=rating, source="simulated-bureau-v1", simulated=True)
    decision = PointsGradingPolicy().grade(auction(), ACTIVE_COMPANY, report, TODAY)
    factor = next(f for f in decision.factors if f.code == code)
    assert factor.points == points
    assert "simulado" in factor.detail
    assert decision.eligible is True


def test_a_sanction_list_never_loaded_leaves_a_note_and_no_points() -> None:
    decision = PointsGradingPolicy().grade(
        auction(), standing(unavailable_sources=("oece-multas",)), None, TODAY
    )
    [note] = [f for f in decision.factors if f.code == "SOURCE_UNAVAILABLE"]
    assert note.points == 0
    assert "OECE" in note.detail
    assert decision.score == 65
