"""The read endpoint and the health endpoints, over ASGI."""
from collections.abc import AsyncIterator

import httpx
import pytest

from assessments.interfaces.dependencies import get_risk_assessment_service
from main import app
from tests.fakes import ServiceUnderTest, auction_created, build_service


@pytest.fixture
async def sut() -> AsyncIterator[ServiceUnderTest]:
    service = build_service()
    app.dependency_overrides[get_risk_assessment_service] = lambda: service.service
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://risk") as http:
        yield http


async def test_reads_the_assessment_of_an_auction(sut: ServiceUnderTest, client: httpx.AsyncClient) -> None:
    await sut.service.assess_auction(**auction_created())

    response = await client.get("/api/v1/risk-assessments/20000000-0000-4000-8000-000000000001")

    assert response.status_code == 200
    body = response.json()
    assert body["assessment_id"].startswith("risk-")
    assert body["eligible"] is True
    assert body["risk_grade"] == "B"
    assert body["score"] == 60
    assert body["provisional"] is False
    assert body["grading_policy"] == "points-v2"
    assert {factor["code"] for factor in body["factors"]} == {
        "DOMICILE_FOUND",
        "COMPANY",
        "NAME_MATCHES",
        "TERM_61_TO_90_DAYS",
    }
    assert body["rejection_code"] is None
    assert body["delivery_status"] == "PENDING"
    assert body["invoice_amount"] == "10000.00"


async def test_an_unknown_auction_is_404(sut: ServiceUnderTest, client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/risk-assessments/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "No risk assessment exists for auction missing"}


async def test_liveness_answers_without_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
