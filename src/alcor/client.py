"""Small asynchronous HTTP client for the Alcor Decision API."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from alcor.contracts import DecisionRequest, DecisionResponse


class DecisionServiceError(RuntimeError):
    """Base class for API errors that must never be treated as permission to delegate."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DecisionServiceUnavailable(DecisionServiceError):
    """The API could not be reached or returned a server error."""


class DecisionServiceRejected(DecisionServiceError):
    """The API rejected malformed, unauthenticated, or unsupported input."""


class InvalidDecisionResponse(DecisionServiceError):
    """The API returned an invalid or incorrectly bound response."""


class AlcorClient:
    """Async client with request/response binding and fail-closed errors."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8085",
        *,
        timeout: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )
        self._timeout = timeout

    async def __aenter__(self) -> AlcorClient:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        timeout = min(self._timeout, max(0.25, request.deadline_ms / 1000 + 0.25))
        try:
            response = await self._client.post(
                "/v1/decisions",
                json=request.model_dump(mode="json"),
                timeout=timeout,
            )
        except httpx.RequestError as exc:
            raise DecisionServiceUnavailable("Alcor decision service is unavailable") from exc

        if response.status_code in {400, 401, 403, 413, 422}:
            raise DecisionServiceRejected(
                "Alcor rejected the decision request",
                status_code=response.status_code,
            )
        if response.status_code >= 500:
            raise DecisionServiceUnavailable(
                "Alcor decision service returned a server error",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise DecisionServiceError(
                "Alcor decision service returned an unexpected error",
                status_code=response.status_code,
            )

        try:
            result = DecisionResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise InvalidDecisionResponse("Alcor returned an invalid response") from exc

        if (
            result.request_id != request.request_id
            or result.context_digest != request.context_digest
        ):
            raise InvalidDecisionResponse("Alcor response does not match this request")
        return result

    async def get_metadata(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/v1/metadata", timeout=self._timeout)
            response.raise_for_status()
            metadata = response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise DecisionServiceUnavailable("Alcor metadata is unavailable") from exc
        except ValueError as exc:
            raise InvalidDecisionResponse("Alcor returned invalid metadata") from exc
        if not isinstance(metadata, dict):
            raise InvalidDecisionResponse("Alcor metadata must be a JSON object")
        return metadata
