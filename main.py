"""Entry point of the Vankoo Risk Service API.

Assembles the application: registers every bounded context's router, the
exception handlers and the event handlers, starts the Kafka consumer, the
delivery worker and the daily refresh of SUNAT's registries, and closes
everything on shutdown. The schema is Alembic's
job (``alembic upgrade head``), never this module's.

Run it with one worker only: the consumer and the delivery worker live in
this process, and each extra worker would run its own. Scale by running more
containers in the same consumer group instead::

    fastapi dev main.py
    fastapi run main.py --workers 1
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from assessments.application.event_handlers import register_event_handlers as register_assessments_event_handlers
from assessments.application.services import RiskAssessmentApplicationService
from assessments.infrastructure.settings import investment_settings
from assessments.interfaces.consumers import AuctionLifecycleConsumer
from assessments.interfaces.dependencies import build_risk_assessment_service
from assessments.interfaces.routes import router as assessments_router
from assessments.interfaces.workers import EvaluationDeliveryWorker
from registries.infrastructure.settings import registry_settings
from registries.interfaces.scheduler import RegistryRefreshScheduler
from shared.application.events import event_bus
from shared.infrastructure.database import engine, session_factory
from shared.infrastructure.settings import kafka_settings, settings
from shared.interfaces.background import BackgroundTask
from shared.interfaces.exception_handlers import register_exception_handlers
from shared.interfaces.health import ReadinessCheck
from shared.interfaces.health import router as health_router

# Uvicorn configures its own loggers only; without this, the application's
# INFO messages (an event handler's, for one) are silently dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
# aiokafka logs every rebalance and fetch at INFO; its warnings are enough.
logging.getLogger("aiokafka").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shutdown work that must happen exactly once per process."""
    investment_client = httpx.AsyncClient(
        base_url=investment_settings.base_url,
        timeout=httpx.Timeout(investment_settings.read_timeout, connect=investment_settings.connect_timeout),
    )
    app.state.investment_client = investment_client

    def build_service(session: AsyncSession) -> RiskAssessmentApplicationService:
        return build_risk_assessment_service(session, investment_client)

    worker = EvaluationDeliveryWorker(session_factory, build_service)
    consumer = AuctionLifecycleConsumer(kafka_settings, session_factory, build_service)
    register_assessments_event_handlers(event_bus, worker.wake)

    tasks: list[BackgroundTask] = []
    checks: dict[str, ReadinessCheck] = {}
    if kafka_settings.consumer_enabled:
        consumer_task = BackgroundTask("auction-lifecycle-consumer", consumer.run)
        tasks.append(consumer_task)
        checks["auction_lifecycle_consumer"] = lambda: consumer.ready
    if investment_settings.delivery_enabled:
        delivery_task = BackgroundTask("evaluation-delivery", worker.run)
        tasks.append(delivery_task)
        checks["evaluation_delivery"] = lambda: delivery_task.running
    if registry_settings.refresh_enabled:
        # Not a readiness check: assessments work (graded C) while the padrón is loading.
        tasks.append(BackgroundTask("registry-refresh", RegistryRefreshScheduler(registry_settings).run))
    app.state.readiness_checks = checks

    for task in tasks:
        task.start()
    try:
        yield
    finally:
        for task in reversed(tasks):
            await task.stop()
        await investment_client.aclose()
        await engine.dispose()


def route_name_as_operation_id(route: APIRoute) -> str:
    """Use the route function's name as its OpenAPI ``operationId``."""
    return route.name


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    generate_unique_id_function=route_name_as_operation_id,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

register_exception_handlers(app)
app.include_router(health_router)
app.include_router(assessments_router)
