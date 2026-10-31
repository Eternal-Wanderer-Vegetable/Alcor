from __future__ import annotations

import asyncio

import httpx
import pytest

from alcor.api import create_app
from alcor.backends.rules import RulesBackend
from alcor.client import (
    AlcorClient,
    DecisionServiceRejected,
    DecisionServiceUnavailable,
    InvalidDecisionResponse,
)
from alcor.engine import DecisionEngine
from tests.helpers import make_request


def test_client_round_trips_through_the_asgi_api() -> None:
    async def run() -> None:
        app = create_app(RulesBackend())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://alcor.test",
        ) as http_client:
            async with AlcorClient(client=http_client) as client:
                result = await client.decide(make_request())
                metadata = await client.get_metadata()

        assert result.request_id == "request-1"
        assert result.context_digest
        assert metadata["backend"] == "rules"
        assert len(metadata["bundle_digest"]) == 64

    asyncio.run(run())


def test_client_rejects_response_bound_to_another_request() -> None:
    request = make_request()
    result = asyncio.run(DecisionEngine(RulesBackend()).decide(request))
    payload = result.model_dump(mode="json")
    payload["request_id"] = "another-request"

    def handler(incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=incoming)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://alcor.test",
        ) as http_client:
            async with AlcorClient(client=http_client) as client:
                with pytest.raises(InvalidDecisionResponse, match="does not match"):
                    await client.decide(request)

    asyncio.run(run())


def test_client_converts_transport_failure_to_unavailable() -> None:
    def handler(incoming: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private transport detail", request=incoming)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://alcor.test",
        ) as http_client:
            async with AlcorClient(client=http_client) as client:
                with pytest.raises(DecisionServiceUnavailable):
                    await client.decide(make_request())

    asyncio.run(run())


def test_client_surfaces_input_rejection_without_a_fallback_decision() -> None:
    def handler(incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "invalid_json"}, request=incoming)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://alcor.test",
        ) as http_client:
            async with AlcorClient(client=http_client) as client:
                with pytest.raises(DecisionServiceRejected) as error:
                    await client.decide(make_request())

        assert error.value.status_code == 422

    asyncio.run(run())
