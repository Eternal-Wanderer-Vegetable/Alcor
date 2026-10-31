"""Backend interface and shared result types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from alcor.contracts import Assessment, DecisionContext, Versions


@dataclass(frozen=True)
class BackendDescriptor:
    backend: str
    model: str
    template: str
    normalizer: str
    bundle: str
    calibration_id: str | None = None
    tokenizer_revision: str | None = None
    max_context_tokens: int | None = None
    bundle_digest: str | None = None

    @property
    def descriptor_digest(self) -> str:
        """Digest the declared version identity when no artifact digest is available."""
        payload = json.dumps(
            {
                "backend": self.backend,
                "model": self.model,
                "template": self.template,
                "normalizer": self.normalizer,
                "bundle": self.bundle,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def versions(self, policy: str) -> Versions:
        return Versions(
            backend=self.backend,
            model=self.model,
            template=self.template,
            normalizer=self.normalizer,
            policy=policy,
            bundle=self.bundle,
        )


@dataclass(frozen=True)
class BackendResult:
    assessment: Assessment
    evidence_message_ids: tuple[str, ...]
    delegation_probability: float | None = None
    calibration_id: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class BackendHealth:
    ready: bool
    backend: str
    detail: str = "ok"


class BackendError(RuntimeError):
    """Base class for expected backend failures."""


class BackendUnavailableError(BackendError):
    """The configured backend cannot currently make a decision."""


class BackendContractError(BackendError):
    """The backend returned a result that violates its declared contract."""


class DecisionBackend(Protocol):
    def describe(self) -> BackendDescriptor: ...

    async def decide(
        self,
        context: DecisionContext,
        *,
        deadline_monotonic: float,
    ) -> BackendResult: ...

    async def health(self) -> BackendHealth: ...
