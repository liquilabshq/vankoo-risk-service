"""Dependency wiring of the Assessments bounded context.

The one place that chooses the concrete adapter for each port, the grading
policy, and the Registries facade the assessments ask about payers. The
consumer, the delivery worker and the routes all build the application
service through :func:`build_risk_assessment_service`.
"""
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from assessments.application.acl import ExternalRegistriesService
from assessments.application.services import RiskAssessmentApplicationService
from assessments.domain.services import PointsGradingPolicy, RiskGradingPolicy
from assessments.infrastructure.clients import HttpxAuctionEvaluationService
from assessments.infrastructure.repositories import SqlAlchemyRiskAssessmentRepository
from registries.interfaces.acl import RegistriesContextFacade
from shared.application.events import event_bus
from shared.infrastructure.messaging import SqlAlchemyInbox
from shared.interfaces.dependencies import SessionDep


def build_grading_policy() -> RiskGradingPolicy:
    """Return the policy that decides on auctions; see ``docs/SCORING_RULES.md``.

    Returns:
        RiskGradingPolicy: The policy in force.
    """
    return PointsGradingPolicy()


def build_risk_assessment_service(
    session: AsyncSession, investment_client: httpx.AsyncClient
) -> RiskAssessmentApplicationService:
    """Build the application service on one session.

    Args:
        session (AsyncSession): The session of the current unit of work.
        investment_client (httpx.AsyncClient): The process-wide client for Investment.

    Returns:
        RiskAssessmentApplicationService: The service for this unit of work.
    """
    return RiskAssessmentApplicationService(
        SqlAlchemyRiskAssessmentRepository(session),
        SqlAlchemyInbox(session),
        ExternalRegistriesService(RegistriesContextFacade(session)),
        HttpxAuctionEvaluationService(investment_client),
        build_grading_policy(),
        session,
        event_bus,
    )


async def get_risk_assessment_service(request: Request, session: SessionDep) -> RiskAssessmentApplicationService:
    """Build the application service on the request's session.

    Args:
        request (Request): The current request; its application holds the Investment client.
        session (AsyncSession): The session of the current request.

    Returns:
        RiskAssessmentApplicationService: The service for this request.
    """
    client: httpx.AsyncClient = request.app.state.investment_client
    return build_risk_assessment_service(session, client)


RiskAssessmentServiceDep = Annotated[RiskAssessmentApplicationService, Depends(get_risk_assessment_service)]
