"""REST routes of the Assessments bounded context.

Assessments are created from Kafka events, never through the API, so the API
only reads. Each route translates the request into one call on the
application service and the result into a response schema.
"""
from fastapi import APIRouter

from assessments.interfaces.dependencies import RiskAssessmentServiceDep
from assessments.interfaces.schemas import RiskAssessmentResponse
from shared.interfaces.schemas import error_responses

router = APIRouter(prefix="/api/v1/risk-assessments", tags=["Risk Assessments"])


@router.get("/{auction_id}", responses=error_responses(400, 404))
async def get_risk_assessment_by_auction_id(
    auction_id: str, service: RiskAssessmentServiceDep
) -> RiskAssessmentResponse:
    """Get the risk assessment of an auction, and whether Investment has received it."""
    return RiskAssessmentResponse.from_entity(await service.get_risk_assessment_by_auction_id(auction_id))
