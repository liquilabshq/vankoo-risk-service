"""Domain services of the Assessments bounded context.

The grading policy is the rule that turns what we know about an auction and
its payer into a decision. It belongs to no single aggregate: it reads facts
Investment published and what SUNAT's registries say. It is a port, so a new
policy replaces it without touching the assessment, the consumer or the
delivery. The rules of the current one are in ``docs/SCORING_RULES.md``.
"""
import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import date
from difflib import SequenceMatcher

from assessments.domain.value_objects import AuctionFacts, GradingDecision, PayerStanding, RiskGrade, ScoreFactor

POINTS_POLICY_VERSION = "points-v1"
BASE_SCORE = 40
GRADE_A_FROM = 75
GRADE_B_FROM = 55
NAME_MATCH_THRESHOLD = 0.85

PAYER_NOT_IN_REGISTRY = "PAYER_NOT_IN_REGISTRY"
PAYER_NOT_ACTIVE = "PAYER_NOT_ACTIVE"
PAYER_DOMICILE_NOT_FOUND = "PAYER_DOMICILE_NOT_FOUND"

ACTIVE_STATUS = "ACTIVO"
FOUND_CONDITION = "HABIDO"
UNVERIFIED_CONDITIONS = ("PENDIENTE", "POR VERIFICAR")
NOT_FOUND_CONDITIONS = ("NO HABIDO", "NO HALLADO")

# Legal-form suffixes that SUNAT and an invoice may write differently
# (``S.A.C.`` against ``SOCIEDAD ANONIMA CERRADA``) and that say nothing about who it is.
_LEGAL_FORMS = (
    "SOCIEDAD COMERCIAL DE RESPONSABILIDAD LIMITADA",
    "EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA",
    "SOCIEDAD DE RESPONSABILIDAD LIMITADA",
    "SOCIEDAD ANONIMA ABIERTA",
    "SOCIEDAD ANONIMA CERRADA",
    "SOCIEDAD ANONIMA",
)
_LEGAL_FORM_TOKENS = frozenset({"SAC", "SA", "SAA", "SRL", "EIRL", "SCRL"})


class RiskGradingPolicy(ABC):
    """Decides whether an auction can be funded, and its grade, with no I/O."""

    @abstractmethod
    def grade(self, facts: AuctionFacts, standing: PayerStanding, today: date) -> GradingDecision:
        """Grade an auction.

        Args:
            facts (AuctionFacts): What Investment published about the auction.
            standing (PayerStanding): What SUNAT says about the payer.
            today (date): The day of the assessment, to count the days to the due date.

        Returns:
            GradingDecision: Eligible with a grade, or rejected with its reason.
        """


class PointsGradingPolicy(RiskGradingPolicy):
    """Grades the payer with points from SUNAT's registries and the invoice's term.

    First a filter: a payer missing from the padrón, not active, or whose fiscal
    address cannot be found makes the invoice not eligible. Then points, from a
    base of 40: being an IGV withholding or perception agent, the address
    condition, company or individual, whether the invoice names the payer as
    SUNAT does, and the days left to the due date. 75 or more is A, 55 or more
    is B, the rest is C. While the padrón has never been loaded, every auction
    is C, never rejected for lack of data.
    """

    def grade(self, facts: AuctionFacts, standing: PayerStanding, today: date) -> GradingDecision:
        ruc = facts.payer.ruc.value
        if not standing.registry_loaded:
            factor = ScoreFactor(
                "REGISTRY_UNAVAILABLE", 0, "El padrón de SUNAT todavía no está cargado: nota conservadora."
            )
            return self._graded(RiskGrade.C, None, (factor,))

        rejection = self._rejection(ruc, standing)
        if rejection is not None:
            code, reason = rejection
            return GradingDecision(
                eligible=False,
                grade=None,
                score=None,
                factors=(ScoreFactor(code, 0, reason),),
                full_balance_outstanding=True,
                policy_version=POINTS_POLICY_VERSION,
                rejection_code=code,
                rejection_reason=reason,
            )

        factors = [
            *self._agent_factors(standing),
            *self._condition_factors(standing),
            *self._taxpayer_type_factors(ruc),
            *self._name_factors(facts.payer.name, standing.name),
            self._term_factor((facts.due_date - today).days),
        ]
        score = BASE_SCORE + sum(factor.points for factor in factors)
        return self._graded(grade_for(score), score, tuple(factors))

    @staticmethod
    def _graded(grade: RiskGrade, score: int | None, factors: tuple[ScoreFactor, ...]) -> GradingDecision:
        return GradingDecision(
            eligible=True,
            grade=grade,
            score=score,
            factors=factors,
            full_balance_outstanding=True,
            policy_version=POINTS_POLICY_VERSION,
        )

    @staticmethod
    def _rejection(ruc: str, standing: PayerStanding) -> tuple[str, str] | None:
        if not standing.found:
            return PAYER_NOT_IN_REGISTRY, f"El RUC del pagador ({ruc}) no figura en el padrón de SUNAT."
        status = (standing.status or "").strip().upper()
        if status != ACTIVE_STATUS:
            return (
                PAYER_NOT_ACTIVE,
                f"El pagador figura en SUNAT con estado «{status or 'desconocido'}»; "
                "solo se financian pagadores activos.",
            )
        condition = (standing.domicile_condition or "").strip().upper()
        if condition.startswith(NOT_FOUND_CONDITIONS):
            return PAYER_DOMICILE_NOT_FOUND, f"El domicilio fiscal del pagador figura en SUNAT como «{condition}»."
        return None

    @staticmethod
    def _agent_factors(standing: PayerStanding) -> list[ScoreFactor]:
        if standing.withholding_agent:
            return [ScoreFactor("WITHHOLDING_AGENT", 20, "SUNAT lo designó agente de retención del IGV.")]
        if standing.perception_agent:
            return [ScoreFactor("PERCEPTION_AGENT", 10, "SUNAT lo designó agente de percepción del IGV.")]
        return []

    @staticmethod
    def _condition_factors(standing: PayerStanding) -> list[ScoreFactor]:
        condition = (standing.domicile_condition or "").strip().upper()
        if condition == FOUND_CONDITION:
            return [ScoreFactor("DOMICILE_FOUND", 10, "Domicilio fiscal HABIDO en SUNAT.")]
        if condition.startswith(UNVERIFIED_CONDITIONS):
            return [ScoreFactor("DOMICILE_UNVERIFIED", -10, f"Domicilio fiscal «{condition}» en SUNAT.")]
        return []

    @staticmethod
    def _taxpayer_type_factors(ruc: str) -> list[ScoreFactor]:
        if ruc.startswith("20"):
            return [ScoreFactor("COMPANY", 5, "El pagador es una persona jurídica (RUC 20).")]
        if ruc.startswith("10"):
            return [ScoreFactor("INDIVIDUAL", -5, "El pagador es una persona natural con negocio (RUC 10).")]
        return []

    @staticmethod
    def _name_factors(invoice_name: str, registered_name: str | None) -> list[ScoreFactor]:
        if not registered_name:
            return []
        if names_match(invoice_name, registered_name):
            return [ScoreFactor("NAME_MATCHES", 5, "La razón social de la factura coincide con la de SUNAT.")]
        return [
            ScoreFactor(
                "NAME_MISMATCH",
                -15,
                f"La factura nombra al pagador «{invoice_name}», pero SUNAT lo registra como «{registered_name}».",
            )
        ]

    @staticmethod
    def _term_factor(days: int) -> ScoreFactor:
        if days <= 30:
            return ScoreFactor("TERM_UP_TO_30_DAYS", 10, f"Vence en {days} días.")
        if days <= 60:
            return ScoreFactor("TERM_31_TO_60_DAYS", 5, f"Vence en {days} días.")
        if days <= 90:
            return ScoreFactor("TERM_61_TO_90_DAYS", 0, f"Vence en {days} días.")
        return ScoreFactor("TERM_OVER_90_DAYS", -10, f"Vence en {days} días.")


def grade_for(score: int) -> RiskGrade:
    """Turn a score into a grade: 75 or more is A, 55 or more is B, the rest is C."""
    if score >= GRADE_A_FROM:
        return RiskGrade.A
    if score >= GRADE_B_FROM:
        return RiskGrade.B
    return RiskGrade.C


def normalize_company_name(name: str) -> str:
    """Write a company name the same way however it was typed.

    Upper case, no accents, no punctuation, and no legal-form suffix, so that
    ``Pagador S.A.C.`` and ``PAGADOR SOCIEDAD ANONIMA CERRADA`` both become ``PAGADOR``.
    """
    text = "".join(c for c in unicodedata.normalize("NFKD", name.upper()) if not unicodedata.combining(c))
    for form in _LEGAL_FORMS:
        text = text.replace(form, " ")
    text = text.replace(".", "")
    tokens = re.sub(r"[^A-Z0-9Ñ]+", " ", text).split()
    return " ".join(token for token in tokens if token not in _LEGAL_FORM_TOKENS)


def names_match(invoice_name: str, registered_name: str) -> bool:
    """Tell whether two names are the same company, allowing for small differences."""
    left, right = normalize_company_name(invoice_name), normalize_company_name(registered_name)
    if not left or not right:
        return False
    return SequenceMatcher(None, left, right).ratio() >= NAME_MATCH_THRESHOLD
