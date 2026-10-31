"""FastAPI application for the Alcor Decision API v0.1."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException

from alcor.backends.base import DecisionBackend
from alcor.backends.rules import RulesBackend
from alcor.contracts import DecisionRequest, DecisionResponse
from alcor.engine import DecisionEngine, EngineSettings
from alcor.policy import POLICY_VERSION


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object repeats a property name."""


class RequestBodyLimitMiddleware:
    """Enforce the protocol's body-size limit, including chunked requests."""

    def __init__(self, app, max_body_bytes: int) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/v1/decisions":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                await self._respond(send, 400, b'{"detail":"invalid_content_length"}')
                return
            if content_length < 0:
                await self._respond(send, 400, b'{"detail":"invalid_content_length"}')
                return
            if content_length > self.max_body_bytes:
                await self._respond(send, 413, b'{"detail":"request_body_too_large"}')
                return

        received: list[dict[str, Any]] = []
        total_bytes = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                received.append(message)
                continue
            total_bytes += len(message.get("body", b""))
            if total_bytes > self.max_body_bytes:
                await self._respond(send, 413, b'{"detail":"request_body_too_large"}')
                return
            received.append(message)
            if not message.get("more_body", False):
                break

        index = 0
        buffered_body = b"".join(
            message.get("body", b"") for message in received if message["type"] == "http.request"
        )
        try:
            json.loads(
                buffered_body,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except DuplicateJSONKeyError:
            await self._respond(send, 422, b'{"detail":"invalid_json"}')
            return
        except json.JSONDecodeError:
            # Let FastAPI produce its normal 422 response for malformed JSON.
            pass
        except (UnicodeDecodeError, ValueError):
            await self._respond(send, 422, b'{"detail":"invalid_json"}')
            return

        async def replay_receive():
            nonlocal index
            if index < len(received):
                message = received[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _respond(send, status_code: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"duplicate JSON property: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def create_app(
    backend: DecisionBackend | None = None,
    *,
    engine_settings: EngineSettings | None = None,
    max_body_bytes: int = 64 * 1024,
) -> FastAPI:
    engine = DecisionEngine(backend or RulesBackend(), settings=engine_settings)
    app = FastAPI(
        title="Alcor Decision API",
        version="0.1.0",
        description="Backend-neutral semantic suggestions. Host policy remains authoritative.",
    )
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=max_body_bytes)
    app.state.engine = engine

    @app.post("/v1/decisions", response_model=DecisionResponse)
    async def decide(decision_request: DecisionRequest) -> DecisionResponse:
        return await engine.decide(decision_request)

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        try:
            health = await engine.health()
        except Exception:
            raise HTTPException(status_code=503, detail="backend_unavailable") from None
        if not health.ready:
            raise HTTPException(status_code=503, detail="backend_not_ready")
        return {"status": "ready", "backend": health.backend}

    @app.get("/v1/metadata")
    async def metadata() -> dict[str, Any]:
        descriptor = engine.describe()
        return {
            "schema_version": "0.1",
            "backend": descriptor.backend,
            "model": descriptor.model,
            "template": descriptor.template,
            "normalizer": descriptor.normalizer,
            "policy": POLICY_VERSION,
            "bundle": descriptor.bundle,
            "bundle_digest": descriptor.bundle_digest,
            "descriptor_digest": descriptor.descriptor_digest,
            "calibration_id": descriptor.calibration_id,
            "tokenizer_revision": descriptor.tokenizer_revision,
            "effective_max_length": descriptor.max_context_tokens,
            "max_body_bytes": max_body_bytes,
            "max_deadline_ms": engine.settings.max_decision_deadline_ms,
            "queue_capacity": engine.settings.queue_capacity,
            "concurrency": engine.settings.concurrency,
        }

    return app


app = create_app()
