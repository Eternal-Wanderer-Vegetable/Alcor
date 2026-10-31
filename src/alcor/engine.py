"""Deadline-aware decision orchestration and bounded in-process admission."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from alcor.backends.base import (
    BackendContractError,
    BackendDescriptor,
    BackendError,
    BackendResult,
    DecisionBackend,
)
from alcor.contracts import (
    Action,
    Assessment,
    DecisionRequest,
    DecisionResponse,
    DecisionStatus,
    ExecutionMode,
    Intent,
    ReasonCode,
    ReferenceStatus,
    RequestRelation,
    Target,
    TaskKind,
)
from alcor.policy import POLICY_VERSION, DecisionPolicy


@dataclass(frozen=True)
class EngineSettings:
    max_decision_deadline_ms: int = 800
    max_queue_wait_ms: int = 100
    queue_capacity: int = 8
    concurrency: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.max_decision_deadline_ms <= 2000:
            raise ValueError("max_decision_deadline_ms must be between 1 and 2000")
        if self.max_queue_wait_ms < 1:
            raise ValueError("max_queue_wait_ms must be positive")
        if self.queue_capacity < 0:
            raise ValueError("queue_capacity cannot be negative")
        if self.concurrency < 1:
            raise ValueError("concurrency must be positive")


class DecisionBusyError(RuntimeError):
    """No worker or bounded queue slot can accept this request."""


class DecisionTimeoutError(RuntimeError):
    """The request budget expired while waiting or deciding."""


class BoundedDecisionExecutor:
    """Bound concurrent decisions and queued work without background retries."""

    def __init__(self, concurrency: int = 1, queue_capacity: int = 8) -> None:
        if concurrency < 1 or queue_capacity < 0:
            raise ValueError("concurrency must be positive and queue capacity non-negative")
        self._concurrency = concurrency
        self._queue_capacity = queue_capacity
        self._active = 0
        self._waiting = 0
        self._condition = asyncio.Condition()

    @property
    def active(self) -> int:
        return self._active

    @property
    def waiting(self) -> int:
        return self._waiting

    async def run(
        self,
        operation,
        *,
        deadline_monotonic: float,
        max_queue_wait_ms: int,
    ):
        loop = asyncio.get_running_loop()
        async with self._condition:
            if self._active < self._concurrency:
                self._active += 1
            else:
                if self._waiting >= self._queue_capacity:
                    raise DecisionBusyError("decision queue is full")
                self._waiting += 1
                queue_deadline = min(
                    deadline_monotonic,
                    loop.time() + max_queue_wait_ms / 1000,
                )
                remaining = queue_deadline - loop.time()
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(lambda: self._active < self._concurrency),
                        timeout=max(0, remaining),
                    )
                except TimeoutError as exc:
                    self._waiting -= 1
                    self._condition.notify_all()
                    if loop.time() >= deadline_monotonic:
                        raise DecisionTimeoutError from exc
                    raise DecisionBusyError("decision queue wait limit exceeded") from exc
                except asyncio.CancelledError:
                    self._waiting -= 1
                    self._condition.notify_all()
                    raise
                self._waiting -= 1
                self._active += 1

        try:
            remaining = deadline_monotonic - loop.time()
            if remaining <= 0:
                raise DecisionTimeoutError
            try:
                return await asyncio.wait_for(operation(), timeout=remaining)
            except TimeoutError as exc:
                raise DecisionTimeoutError from exc
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify_all()


class DecisionEngine:
    def __init__(
        self,
        backend: DecisionBackend,
        *,
        settings: EngineSettings | None = None,
        policy: DecisionPolicy | None = None,
    ) -> None:
        self.backend = backend
        self.settings = settings or EngineSettings()
        self.policy = policy or DecisionPolicy()
        self.executor = BoundedDecisionExecutor(
            concurrency=self.settings.concurrency,
            queue_capacity=self.settings.queue_capacity,
        )

    async def decide(self, request: DecisionRequest) -> DecisionResponse:
        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        now = loop.time()
        deadline = min(
            now + request.deadline_ms / 1000,
            now + self.settings.max_decision_deadline_ms / 1000,
        )
        descriptor = self.describe()
        if descriptor.backend == "unavailable":
            return self._failure(
                request,
                descriptor,
                ReasonCode.BACKEND_UNAVAILABLE,
                elapsed_ms=self._elapsed_ms(started),
            )
        preflight = self.policy.preflight(request, descriptor)
        if preflight is not None:
            return preflight.model_copy(update={"elapsed_ms": self._elapsed_ms(started)})

        try:
            result = await self.executor.run(
                lambda: self.backend.decide(request.context, deadline_monotonic=deadline),
                deadline_monotonic=deadline,
                max_queue_wait_ms=self.settings.max_queue_wait_ms,
            )
            if not isinstance(result, BackendResult):
                raise BackendContractError("backend returned a non-BackendResult value")
            if not isinstance(result.assessment, Assessment):
                raise BackendContractError("backend result has an invalid assessment")
            return self.policy.compose(
                request,
                result,
                descriptor,
                elapsed_ms=self._elapsed_ms(started),
            )
        except DecisionBusyError:
            return self._failure(
                request,
                descriptor,
                ReasonCode.BACKEND_BUSY,
                elapsed_ms=self._elapsed_ms(started),
            )
        except DecisionTimeoutError:
            return self._failure(
                request,
                descriptor,
                ReasonCode.BACKEND_TIMEOUT,
                elapsed_ms=self._elapsed_ms(started),
            )
        except BackendContractError:
            return self._failure(
                request,
                descriptor,
                ReasonCode.INVALID_BACKEND_RESPONSE,
                elapsed_ms=self._elapsed_ms(started),
            )
        except BackendError:
            return self._failure(
                request,
                descriptor,
                ReasonCode.BACKEND_UNAVAILABLE,
                elapsed_ms=self._elapsed_ms(started),
            )
        except Exception:
            return self._failure(
                request,
                descriptor,
                ReasonCode.BACKEND_UNAVAILABLE,
                elapsed_ms=self._elapsed_ms(started),
            )

    async def health(self):
        descriptor = self.describe()
        if descriptor.backend == "unavailable":
            from alcor.backends.base import BackendHealth

            return BackendHealth(ready=False, backend="unavailable", detail="metadata_unavailable")
        try:
            return await self.backend.health()
        except Exception:
            from alcor.backends.base import BackendHealth

            return BackendHealth(
                ready=False,
                backend=descriptor.backend,
                detail="health_probe_failed",
            )

    def describe(self) -> BackendDescriptor:
        try:
            descriptor = self.backend.describe()
            if not isinstance(descriptor, BackendDescriptor):
                raise TypeError("backend did not return BackendDescriptor")
            descriptor.versions(POLICY_VERSION)
            if descriptor.bundle_digest is not None and not re.fullmatch(
                r"[a-f0-9]{64}",
                descriptor.bundle_digest,
            ):
                raise ValueError("backend bundle digest must be a lowercase SHA-256")
            _ = descriptor.descriptor_digest
            return descriptor
        except Exception:
            return BackendDescriptor(
                backend="unavailable",
                model="unknown",
                template="unknown",
                normalizer="context-v0.1",
                bundle="unknown",
            )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return max(0.0, (time.perf_counter() - started) * 1000)

    @staticmethod
    def _failure(
        request: DecisionRequest,
        descriptor: BackendDescriptor,
        reason: ReasonCode,
        *,
        elapsed_ms: float,
    ) -> DecisionResponse:
        return DecisionResponse(
            schema_version="0.1",
            request_id=request.request_id,
            context_digest=request.context_digest,
            status=DecisionStatus.UNKNOWN,
            assessment=Assessment(
                intent=Intent.UNKNOWN,
                task_kind=TaskKind.UNKNOWN,
                execution_mode=ExecutionMode.UNKNOWN,
                reference_status=ReferenceStatus.MISSING,
                request_relation=RequestRelation.UNKNOWN,
            ),
            recommendation={"action": Action.ABSTAIN, "target": Target.NONE, "mode": "none"},
            delegation_probability=None,
            calibration_id=None,
            reason_codes=[reason],
            evidence_message_ids=[],
            versions=descriptor.versions(POLICY_VERSION),
            elapsed_ms=elapsed_ms,
        )
