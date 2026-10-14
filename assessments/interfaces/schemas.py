"""Response schemas of the Assessments REST API."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from assessments.domain.entities import RiskAssessment
from assessments.domain.value_objects import Currency, DeliveryStatus, RiskGrade


class RiskAssessmentResponse(BaseModel):
    """A risk assessment as the API returns it.

    ``provisional`` is true while the grade comes from the stand-in policy and
    says nothing about the payer.
    """

    assessment_id: str
    auction_id: str
    invoice_id: str
    mype_id: str
    payer_ruc: str
    payer_name: str
    due_date: date
    invoice_amount: Decimal
    currency: Currency
    green_certified: bool
    risk_grade: RiskGrade
    full_balance_outstanding: bool
    grading_policy: str
    provisional: bool
    assessed_at: datetime
    delivery_status: DeliveryStatus
    delivery_attempts: int
    next_delivery_at: datetime | None
    last_delivery_error: str | None
    delivered_at: datetime | None
    investment_auction_status: str | None

    @classmethod
    def from_entity(cls, assessment: RiskAssessment) -> "RiskAssessmentResponse":
        """Build the response from the aggregate.

        Args:
            assessment (RiskAssessment): A stored assessment.

        Returns:
            RiskAssessmentResponse: Its public representation.
        """
        facts = assessment.facts
        return cls(
            assessment_id=assessment.assessment_id.value,
            auction_id=facts.auction_id.value,
            invoice_id=facts.invoice_id,
            mype_id=facts.mype_id,
            payer_ruc=facts.payer.ruc.value,
            payer_name=facts.payer.name,
            due_date=facts.due_date,
            invoice_amount=facts.invoice_amount.amount,
            currency=facts.invoice_amount.currency,
            green_certified=facts.green_certified,
            risk_grade=assessment.grade,
            full_balance_outstanding=assessment.decision.full_balance_outstanding,
            grading_policy=assessment.decision.policy_version,
            provisional=assessment.decision.provisional,
            assessed_at=assessment.assessed_at,
            delivery_status=assessment.delivery_status,
            delivery_attempts=assessment.delivery_attempts,
            next_delivery_at=assessment.next_delivery_at,
            last_delivery_error=assessment.last_delivery_error,
            delivered_at=assessment.delivered_at,
            investment_auction_status=assessment.investment_auction_status,
        )
