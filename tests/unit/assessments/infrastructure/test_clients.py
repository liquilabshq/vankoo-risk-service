"""The Investment adapter: what it sends, and how it reads each answer."""
import json
from datetime import UTC, datetime

import httpx
import pytest

from assessments.application.outbound_services import EvaluationOutcomeKind, InvestmentUnavailableError
from assessments.infrastructure.clients import HttpxAuctionEvaluationService, format_instant

ASSESSED_AT = datetime(2026, 10, 14, 18, 0, 0, 123456, tzinfo=UTC)


async def submit(handler: httpx.MockTransport) -> tuple[EvaluationOutcomeKind, str | None, str | None]:
    async with httpx.AsyncClient(base_url="http://investment", transport=handler) as client:
        outcome = await HttpxAuctionEvaluationService(client).submit(
            auction_id="auction-1",
            assessment_id="risk-1",
            risk_grade="B",
            full_balance_outstanding=True,
            assessed_at=ASSESSED_AT,
        )
    return outcome.kind, outcome.auction_status, outcome.message


async def test_sends_the_evaluation_to_the_internal_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "auction-1", "status": "DRAFT", "assessmentId": "risk-1"})

    kind, status, _ = await submit(httpx.MockTransport(handler))

    [request] = seen
    assert request.method == "PUT"
    assert request.url.path == "/api/v1/internal/auctions/auction-1/evaluation"
    assert json.loads(request.content) == {
        "assessmentId": "risk-1",
        "riskGrade": "B",
        "fullBalanceOutstanding": True,
        "assessedAt": "2026-10-14T18:00:00.123Z",
    }
    assert kind is EvaluationOutcomeKind.ACCEPTED
    assert status == "DRAFT"


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (409, {"message": "Auction can no longer be evaluated"}, "HTTP 409: Auction can no longer be evaluated"),
        (404, {"message": "Auction not found: auction-1"}, "HTTP 404: Auction not found: auction-1"),
        (400, {"message": "Validación fallida", "errors": {"riskGrade": "must not be null"}}, "HTTP 400: Validación"),
    ],
)
async def test_final_refusals_are_refused(status: int, body: dict[str, object], expected: str) -> None:
    kind, _, message = await submit(httpx.MockTransport(lambda request: httpx.Response(status, json=body)))
    assert kind is EvaluationOutcomeKind.REFUSED
    assert message is not None and message.startswith(expected)


async def test_server_errors_are_retried() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="Service Unavailable"))
    with pytest.raises(InvestmentUnavailableError, match="HTTP 503"):
        await submit(transport)


async def test_connection_failures_are_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(InvestmentUnavailableError, match="ConnectTimeout"):
        await submit(httpx.MockTransport(handler))


def test_instants_are_written_in_utc_with_milliseconds() -> None:
    assert format_instant(ASSESSED_AT) == "2026-10-14T18:00:00.123Z"
