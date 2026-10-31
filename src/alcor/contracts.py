"""Strict Python contracts for Decision API v0.1."""

from __future__ import annotations

import hmac
import json
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


MessageId = Annotated[str, Field(min_length=1, max_length=128, strict=True)]
RequestId = Annotated[str, Field(min_length=1, max_length=128, strict=True)]
ContextDigest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$", strict=True)]


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class SourceKind(StrEnum):
    DIRECT = "direct"
    QUOTED = "quoted"
    NOTIFICATION = "notification"
    AGENT_RESULT = "agent_result"


class Trigger(StrEnum):
    REPLY = "reply"
    PROACTIVE = "proactive"
    PASSIVE = "passive"
    NOTIFICATION = "notification"


class Integrity(StrEnum):
    COMPLETE = "complete"
    BUDGET_EXCEEDED = "budget_exceeded"
    MISSING_REFERENCE = "missing_reference"
    UNKNOWN = "unknown"


class CodingAgentState(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Intent(StrEnum):
    CHAT = "chat"
    DISCUSS = "discuss"
    EXPLAIN = "explain"
    EXECUTE = "execute"
    UNKNOWN = "unknown"


class TaskKind(StrEnum):
    KNOWLEDGE = "knowledge"
    CODE_SAMPLE = "code_sample"
    REPOSITORY_INSPECTION = "repository_inspection"
    REPOSITORY_CHANGE = "repository_change"
    RESEARCH = "research"
    UNKNOWN = "unknown"


class ExecutionMode(StrEnum):
    NONE = "none"
    INSPECT = "inspect"
    MODIFY = "modify"
    UNKNOWN = "unknown"


class ReferenceStatus(StrEnum):
    COMPLETE = "complete"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


class RequestRelation(StrEnum):
    SELF_REQUEST = "self_request"
    QUOTATION = "quotation"
    HYPOTHETICAL = "hypothetical"
    UNKNOWN = "unknown"


class DecisionStatus(StrEnum):
    DECIDED = "decided"
    UNKNOWN = "unknown"


class Action(StrEnum):
    CHAT = "chat"
    DELEGATE = "delegate"
    CLARIFY = "clarify"
    ABSTAIN = "abstain"


class Target(StrEnum):
    NONE = "none"
    CODING_AGENT = "coding_agent"


class ReasonCode(StrEnum):
    DISCUSSION_ONLY = "discussion_only"
    KNOWLEDGE_OR_EXAMPLE = "knowledge_or_example"
    EXECUTION_REQUESTED = "execution_requested"
    MISSING_CONTEXT = "missing_context"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    QUOTED_OR_HYPOTHETICAL = "quoted_or_hypothetical"
    LOCAL_TOOL_AVAILABLE = "local_tool_available"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"
    UPSTREAM_TRUNCATED = "upstream_truncated"
    LOW_CONFIDENCE = "low_confidence"
    INCONSISTENT_ASSESSMENT = "inconsistent_assessment"
    BACKEND_TIMEOUT = "backend_timeout"
    BACKEND_BUSY = "backend_busy"
    INVALID_BACKEND_RESPONSE = "invalid_backend_response"
    VERSION_MISMATCH = "version_mismatch"
    MISSING_METADATA = "missing_metadata"
    UNTRUSTED_TRIGGER = "untrusted_trigger"
    UNKNOWN = "unknown"


class Message(StrictModel):
    message_id: MessageId
    speaker_id: MessageId
    role: Role
    source_kind: SourceKind
    text: Annotated[str, Field(min_length=1, max_length=16000, strict=True)]


class ProposalReference(StrictModel):
    proposal_id: MessageId
    owner_id: MessageId
    revision: int = Field(ge=1, strict=True)
    content_digest: ContextDigest
    scope: Annotated[str, Field(min_length=1, max_length=2000, strict=True)]
    message_ids: list[MessageId] = Field(max_length=16)

    @model_validator(mode="after")
    def unique_message_ids(self) -> Self:
        if len(self.message_ids) != len(set(self.message_ids)):
            raise ValueError("proposal message_ids must be unique")
        return self


class HostFacts(StrictModel):
    trigger: Trigger
    workspace_bound: bool = Field(strict=True)
    coding_agent_state: CodingAgentState
    deterministic_local_tool: bool = Field(strict=True)


class DecisionContext(StrictModel):
    current_message: Message
    history: list[Message] = Field(max_length=32)
    proposal: ProposalReference | None
    integrity: Integrity
    host_facts: HostFacts

    @model_validator(mode="after")
    def validate_message_ownership_and_ids(self) -> Self:
        messages = [self.current_message, *self.history]
        message_ids = [message.message_id for message in messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("current_message and history message_ids must be unique")

        if self.proposal is not None:
            if self.proposal.owner_id != self.current_message.speaker_id:
                raise ValueError("proposal owner must match the current speaker")
        return self


def canonical_context_bytes(context: DecisionContext) -> bytes:
    """Serialize context exactly as specified by protocol v0.1."""
    payload = context.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def context_digest(context: DecisionContext) -> str:
    return sha256(canonical_context_bytes(context)).hexdigest()


class DecisionRequest(StrictModel):
    schema_version: Literal["0.1"]
    request_id: RequestId
    context_digest: ContextDigest
    deadline_ms: int = Field(ge=1, le=2000, strict=True)
    context: DecisionContext

    @model_validator(mode="after")
    def bind_context_digest(self) -> Self:
        expected = context_digest(self.context)
        if not hmac.compare_digest(self.context_digest, expected):
            raise ValueError("context_digest does not match normalized context")
        return self


class Assessment(StrictModel):
    intent: Intent
    task_kind: TaskKind
    execution_mode: ExecutionMode
    reference_status: ReferenceStatus
    request_relation: RequestRelation


class Recommendation(StrictModel):
    action: Action
    target: Target
    mode: Literal["none", "inspect", "modify"]


class Versions(StrictModel):
    backend: Annotated[str, Field(min_length=1, max_length=200, strict=True)]
    model: Annotated[str, Field(min_length=1, max_length=200, strict=True)]
    template: Annotated[str, Field(min_length=1, max_length=200, strict=True)]
    normalizer: Annotated[str, Field(min_length=1, max_length=200, strict=True)]
    policy: Annotated[str, Field(min_length=1, max_length=200, strict=True)]
    bundle: Annotated[str, Field(min_length=1, max_length=200, strict=True)]


class DecisionResponse(StrictModel):
    schema_version: Literal["0.1"]
    request_id: RequestId
    context_digest: ContextDigest
    status: DecisionStatus
    assessment: Assessment
    recommendation: Recommendation
    delegation_probability: float | None = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        strict=True,
    )
    calibration_id: Annotated[str | None, Field(min_length=1, max_length=200, strict=True)]
    reason_codes: list[ReasonCode] = Field(min_length=1, max_length=8)
    evidence_message_ids: list[MessageId] = Field(max_length=16)
    versions: Versions
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def enforce_cross_field_contract(self) -> Self:
        action = self.recommendation.action
        mode = self.recommendation.mode

        if (self.delegation_probability is None) != (self.calibration_id is None):
            raise ValueError("delegation_probability and calibration_id must both be null or set")

        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        if len(self.evidence_message_ids) != len(set(self.evidence_message_ids)):
            raise ValueError("evidence_message_ids must be unique")

        if self.status is DecisionStatus.UNKNOWN:
            if (
                action is not Action.ABSTAIN
                or self.recommendation.target is not Target.NONE
                or mode != "none"
            ):
                raise ValueError("unknown status requires abstain/none/none")

        if action is Action.DELEGATE:
            if self.status is not DecisionStatus.DECIDED:
                raise ValueError("delegate requires decided status")
            if self.recommendation.target is not Target.CODING_AGENT or mode not in {
                "inspect",
                "modify",
            }:
                raise ValueError("delegate requires coding_agent and inspect/modify mode")
            if (
                self.assessment.intent is not Intent.EXECUTE
                or self.assessment.reference_status is not ReferenceStatus.COMPLETE
                or self.assessment.request_relation is not RequestRelation.SELF_REQUEST
            ):
                raise ValueError("delegate requires a complete, current self-request to execute")

        elif self.recommendation.target is not Target.NONE or mode != "none":
            raise ValueError("non-delegate recommendations require target/mode none")

        if mode == "inspect" and (
            self.assessment.task_kind is not TaskKind.REPOSITORY_INSPECTION
            or self.assessment.execution_mode is not ExecutionMode.INSPECT
        ):
            raise ValueError("inspect mode must match repository_inspection/inspect assessment")
        if mode == "modify" and (
            self.assessment.task_kind is not TaskKind.REPOSITORY_CHANGE
            or self.assessment.execution_mode is not ExecutionMode.MODIFY
        ):
            raise ValueError("modify mode must match repository_change/modify assessment")

        return self


def evidence_ids(context: DecisionContext) -> set[str]:
    """Return all message IDs an output may cite, including trusted proposal references."""
    result = {context.current_message.message_id}
    result.update(message.message_id for message in context.history)
    if context.proposal is not None:
        result.update(context.proposal.message_ids)
    return result
