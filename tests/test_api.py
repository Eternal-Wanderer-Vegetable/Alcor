from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import httpx
import jsonschema

from alcor.api import create_app
from alcor.backends.base import BackendDescriptor, BackendHealth, BackendResult
from alcor.backends.rules import RulesBackend
from alcor.contracts import (
    Assessment,
    DecisionStatus,
    ExecutionMode,
    Intent,
    ReferenceStatus,
    RequestRelation,
    TaskKind,
)
from alcor.engine import DecisionEngine, EngineSettings
from tests.helpers import make_request

ROOT = Path(__file__).resolve().parents[1]


class StubBackend:
    def __init__(self, *, delay: float = 0, ready: bool = True) -> None:
        self.delay = delay
        self.ready = ready
        self.calls = 0
        self.started = threading.Event()
        self._rules = RulesBackend()

    def describe(self) -> BackendDescriptor:
        return self._rules.describe()

    async def decide(self, context, *, deadline_monotonic: float) -> BackendResult:
        self.calls += 1
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        return await self._rules.decide(context, deadline_monotonic=deadline_monotonic)

    async def health(self) -> BackendHealth:
        return BackendHealth(ready=self.ready, backend="rules")


async def _post_json(app, payload):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://alcor.test",
    ) as client:
        return await client.post("/v1/decisions", json=payload)


def post_json(app, payload):
    return asyncio.run(_post_json(app, payload))


def test_api_returns_decision_that_matches_locked_schema_example() -> None:
    app = create_app()
    request = make_request(text="帮我查一下这个仓库的内存泄漏，只调查，不修改文件。")
    response = post_json(app, request.model_dump(mode="json"))

    assert response.status_code == 200
    result = response.json()
    schema = json.loads(
        (ROOT / "schemas" / "decision-response.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(result)
    assert result["request_id"] == request.request_id
    assert result["context_digest"] == request.context_digest


def test_openapi_exposes_the_decision_request_contract() -> None:
    app = create_app()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://alcor.test",
        ) as client:
            return await client.get("/openapi.json")

    response = asyncio.run(run())

    assert response.status_code == 200
    operation = response.json()["paths"]["/v1/decisions"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DecisionRequest"
    )


def test_invalid_digest_and_unknown_properties_are_rejected() -> None:
    app = create_app()
    request = make_request()
    payload = request.model_dump(mode="json")
    payload["context_digest"] = "0" * 64
    bad_digest = post_json(app, payload)

    payload = request.model_dump(mode="json")
    payload["authorization"] = "administrator"
    extra_field = post_json(app, payload)

    assert bad_digest.status_code == 422
    assert extra_field.status_code == 422


def test_duplicate_json_keys_are_rejected() -> None:
    app = create_app()
    payload = make_request().model_dump_json()
    duplicate = payload.replace(
        '"request_id":"request-1"',
        '"request_id":"untrusted","request_id":"request-1"',
        1,
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://alcor.test",
        ) as client:
            return await client.post(
                "/v1/decisions",
                content=duplicate,
                headers={"content-type": "application/json"},
            )

    response = asyncio.run(run())

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_json"


def test_request_body_over_64_kib_is_rejected_before_validation() -> None:
    app = create_app(max_body_bytes=64 * 1024)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://alcor.test",
        ) as client:
            return await client.post(
                "/v1/decisions",
                content=b"x" * (64 * 1024 + 1),
                headers={"content-type": "application/json"},
            )

    response = asyncio.run(run())

    assert response.status_code == 413
    assert response.json()["detail"] == "request_body_too_large"


def test_live_ready_and_metadata_endpoints_report_separate_states() -> None:
    app = create_app(StubBackend(ready=False))

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://alcor.test",
        ) as client:
            return (
                await client.get("/health/live"),
                await client.get("/health/ready"),
                await client.get("/v1/metadata"),
            )

    live, ready, metadata = asyncio.run(run())

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert metadata.status_code == 200
    assert metadata.json()["calibration_id"] is None
    assert metadata.json()["effective_max_length"] is None
    assert len(metadata.json()["bundle_digest"]) == 64


def test_preflight_abstention_does_not_call_backend() -> None:
    backend = StubBackend()
    app = create_app(backend)
    request = make_request(deterministic_local_tool=True)
    response = post_json(app, request.model_dump(mode="json"))

    assert response.status_code == 200
    assert backend.calls == 0
    assert response.json()["reason_codes"] == ["local_tool_available"]


def test_api_preserves_per_request_ids_and_context_digests() -> None:
    app = create_app()
    requests = [
        make_request(request_id="request-a", message_id="message-a"),
        make_request(request_id="request-b", message_id="message-b"),
    ]

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://alcor.test",
        ) as client:
            return [
                await client.post("/v1/decisions", json=request.model_dump(mode="json"))
                for request in requests
            ]

    responses = asyncio.run(run())

    assert [response.status_code for response in responses] == [200, 200]
    for request, response in zip(requests, responses, strict=True):
        assert response.json()["request_id"] == request.request_id
        assert response.json()["context_digest"] == request.context_digest
        assert response.json()["evidence_message_ids"] == [
            request.context.current_message.message_id
        ]


def test_backend_result_with_truncation_abstains() -> None:
    class TruncatedBackend(StubBackend):
        async def decide(self, context, *, deadline_monotonic: float) -> BackendResult:
            assessment = Assessment(
                intent=Intent.EXECUTE,
                task_kind=TaskKind.REPOSITORY_INSPECTION,
                execution_mode=ExecutionMode.INSPECT,
                reference_status=ReferenceStatus.COMPLETE,
                request_relation=RequestRelation.SELF_REQUEST,
            )
            return BackendResult(
                assessment=assessment,
                evidence_message_ids=(context.current_message.message_id,),
                truncated=True,
            )

    app = create_app(TruncatedBackend())
    request = make_request()
    response = post_json(app, request.model_dump(mode="json"))

    assert response.status_code == 200
    assert response.json()["status"] == DecisionStatus.UNKNOWN.value
    assert response.json()["recommendation"]["action"] == "abstain"
    assert response.json()["reason_codes"] == ["upstream_truncated"]


def test_bounded_queue_reports_busy_without_running_another_backend_call() -> None:
    backend = StubBackend(delay=0.1)
    settings = EngineSettings(
        max_decision_deadline_ms=1000,
        max_queue_wait_ms=200,
        queue_capacity=0,
        concurrency=1,
    )
    app = create_app(backend, engine_settings=settings)
    engine: DecisionEngine = app.state.engine
    engine.executor._active = 1
    request = make_request()

    response = post_json(app, request.model_dump(mode="json"))
    engine.executor._active = 0

    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert response.json()["recommendation"]["action"] == "abstain"
    assert response.json()["reason_codes"] == ["backend_busy"]
    assert backend.calls == 0


def test_queued_requests_share_deadline_and_full_queue_returns_busy() -> None:
    async def run() -> None:
        backend = StubBackend(delay=0.05)
        settings = EngineSettings(
            max_decision_deadline_ms=1500,
            max_queue_wait_ms=500,
            queue_capacity=1,
            concurrency=1,
        )
        app = create_app(backend, engine_settings=settings)
        requests = [
            make_request(request_id="request-a", message_id="message-a"),
            make_request(request_id="request-b", message_id="message-b"),
            make_request(request_id="request-c", message_id="message-c"),
        ]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://alcor.test",
        ) as client:
            first = asyncio.create_task(
                client.post("/v1/decisions", json=requests[0].model_dump(mode="json"))
            )
            while not backend.started.is_set():
                await asyncio.sleep(0)

            second = asyncio.create_task(
                client.post("/v1/decisions", json=requests[1].model_dump(mode="json"))
            )
            while app.state.engine.executor.waiting == 0:
                await asyncio.sleep(0)

            full = await client.post(
                "/v1/decisions",
                json=requests[2].model_dump(mode="json"),
            )
            first_result, second_result = await asyncio.gather(first, second)

        assert full.json()["reason_codes"] == ["backend_busy"]
        assert first_result.status_code == second_result.status_code == 200
        assert first_result.json()["request_id"] == requests[0].request_id
        assert second_result.json()["request_id"] == requests[1].request_id
        assert backend.calls == 2

    asyncio.run(run())
