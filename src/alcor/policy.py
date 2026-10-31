"""Deterministic composition of backend assessments and trusted host facts."""

from __future__ import annotations

from alcor.backends.base import BackendDescriptor, BackendResult
from alcor.contracts import (
    Action,
    Assessment,
    CodingAgentState,
    DecisionContext,
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
    Trigger,
)

POLICY_VERSION = "policy-v0.1"


class DecisionPolicy:
    """Apply fixed safety and scope rules after a semantic backend responds."""

    def preflight(
        self,
        request: DecisionRequest,
        descriptor: BackendDescriptor,
        *,
        elapsed_ms: float = 0,
    ) -> DecisionResponse | None:
        context = request.context
        message = context.current_message

        if (
            context.host_facts.trigger is not Trigger.REPLY
            or message.role.value != "user"
            or message.source_kind.value in {"notification", "agent_result"}
        ):
            return self._response(
                request,
                descriptor,
                Assessment(
                    intent=Intent.UNKNOWN,
                    task_kind=TaskKind.UNKNOWN,
                    execution_mode=ExecutionMode.UNKNOWN,
                    reference_status=ReferenceStatus.MISSING,
                    request_relation=RequestRelation.UNKNOWN,
                ),
                action=Action.ABSTAIN,
                reason=ReasonCode.UNTRUSTED_TRIGGER,
                status=DecisionStatus.UNKNOWN,
                elapsed_ms=elapsed_ms,
            )

        if message.source_kind.value == "quoted":
            return self._response(
                request,
                descriptor,
                Assessment(
                    intent=Intent.DISCUSS,
                    task_kind=TaskKind.UNKNOWN,
                    execution_mode=ExecutionMode.NONE,
                    reference_status=ReferenceStatus.COMPLETE,
                    request_relation=RequestRelation.QUOTATION,
                ),
                action=Action.CHAT,
                reason=ReasonCode.QUOTED_OR_HYPOTHETICAL,
                elapsed_ms=elapsed_ms,
            )

        if context.integrity.value != "complete":
            reason = {
                "budget_exceeded": ReasonCode.CONTEXT_BUDGET_EXCEEDED,
                "missing_reference": ReasonCode.MISSING_CONTEXT,
            }.get(context.integrity.value, ReasonCode.UNKNOWN)
            return self._response(
                request,
                descriptor,
                Assessment(
                    intent=Intent.UNKNOWN,
                    task_kind=TaskKind.UNKNOWN,
                    execution_mode=ExecutionMode.UNKNOWN,
                    reference_status=ReferenceStatus.MISSING,
                    request_relation=RequestRelation.UNKNOWN,
                ),
                action=Action.ABSTAIN,
                reason=reason,
                status=DecisionStatus.UNKNOWN,
                elapsed_ms=elapsed_ms,
            )

        if context.host_facts.deterministic_local_tool:
            return self._response(
                request,
                descriptor,
                Assessment(
                    intent=Intent.CHAT,
                    task_kind=TaskKind.KNOWLEDGE,
                    execution_mode=ExecutionMode.NONE,
                    reference_status=ReferenceStatus.COMPLETE,
                    request_relation=RequestRelation.SELF_REQUEST,
                ),
                action=Action.CHAT,
                reason=ReasonCode.LOCAL_TOOL_AVAILABLE,
                elapsed_ms=elapsed_ms,
            )

        return None

    def compose(
        self,
        request: DecisionRequest,
        result: BackendResult,
        descriptor: BackendDescriptor,
        *,
        elapsed_ms: float,
    ) -> DecisionResponse:
        assessment = result.assessment

        if result.truncated:
            return self._unknown(
                request,
                descriptor,
                assessment,
                ReasonCode.UPSTREAM_TRUNCATED,
                elapsed_ms,
            )

        if not set(result.evidence_message_ids).issubset(
            self._available_evidence_ids(request.context)
        ):
            return self._unknown(
                request,
                descriptor,
                assessment,
                ReasonCode.INVALID_BACKEND_RESPONSE,
                elapsed_ms,
            )

        if (result.delegation_probability is None) != (result.calibration_id is None):
            return self._unknown(
                request,
                descriptor,
                assessment,
                ReasonCode.MISSING_METADATA,
                elapsed_ms,
            )
        if (
            result.delegation_probability is not None
            and result.calibration_id != descriptor.calibration_id
        ):
            return self._unknown(
                request,
                descriptor,
                assessment,
                ReasonCode.VERSION_MISMATCH,
                elapsed_ms,
            )

        reason = ReasonCode.UNKNOWN
        action = Action.ABSTAIN
        status = DecisionStatus.UNKNOWN

        if assessment.request_relation in {RequestRelation.QUOTATION, RequestRelation.HYPOTHETICAL}:
            action = Action.CHAT
            status = DecisionStatus.DECIDED
            reason = ReasonCode.QUOTED_OR_HYPOTHETICAL
        elif assessment.request_relation is RequestRelation.UNKNOWN:
            reason = ReasonCode.UNKNOWN
        elif assessment.execution_mode in {ExecutionMode.INSPECT, ExecutionMode.MODIFY} and (
            assessment.intent is not Intent.EXECUTE
        ):
            reason = ReasonCode.INCONSISTENT_ASSESSMENT
        elif assessment.intent in {Intent.CHAT, Intent.DISCUSS, Intent.EXPLAIN}:
            action = Action.CHAT
            status = DecisionStatus.DECIDED
            reason = (
                ReasonCode.DISCUSSION_ONLY
                if assessment.intent is Intent.DISCUSS
                else ReasonCode.KNOWLEDGE_OR_EXAMPLE
            )
        elif assessment.intent is Intent.UNKNOWN:
            reason = ReasonCode.UNKNOWN
        elif assessment.task_kind is TaskKind.RESEARCH:
            reason = ReasonCode.UNSUPPORTED_SCOPE
        elif assessment.intent is Intent.EXECUTE:
            if assessment.reference_status is ReferenceStatus.MISSING:
                action = Action.CLARIFY
                status = DecisionStatus.DECIDED
                reason = ReasonCode.MISSING_CONTEXT
            elif assessment.reference_status is ReferenceStatus.AMBIGUOUS:
                action = Action.CLARIFY
                status = DecisionStatus.DECIDED
                reason = ReasonCode.AMBIGUOUS_REFERENCE
            elif assessment.task_kind not in {
                TaskKind.REPOSITORY_INSPECTION,
                TaskKind.REPOSITORY_CHANGE,
            }:
                action = (
                    Action.CHAT
                    if assessment.task_kind
                    in {
                        TaskKind.KNOWLEDGE,
                        TaskKind.CODE_SAMPLE,
                    }
                    else Action.ABSTAIN
                )
                status = DecisionStatus.DECIDED if action is Action.CHAT else DecisionStatus.UNKNOWN
                reason = (
                    ReasonCode.KNOWLEDGE_OR_EXAMPLE
                    if action is Action.CHAT
                    else ReasonCode.UNSUPPORTED_SCOPE
                )
            elif not self._assessment_is_consistent(assessment):
                reason = ReasonCode.INCONSISTENT_ASSESSMENT
            elif not request.context.host_facts.workspace_bound:
                action = Action.CLARIFY
                status = DecisionStatus.DECIDED
                reason = ReasonCode.MISSING_CONTEXT
            elif request.context.host_facts.coding_agent_state is not CodingAgentState.READY:
                reason = ReasonCode.BACKEND_UNAVAILABLE
            else:
                action = Action.DELEGATE
                status = DecisionStatus.DECIDED
                reason = ReasonCode.EXECUTION_REQUESTED

        if status is DecisionStatus.UNKNOWN:
            return self._response(
                request,
                descriptor,
                assessment,
                action=Action.ABSTAIN,
                reason=reason,
                status=DecisionStatus.UNKNOWN,
                elapsed_ms=elapsed_ms,
                evidence_ids=result.evidence_message_ids,
            )

        mode = "none"
        target = Target.NONE
        if action is Action.DELEGATE:
            target = Target.CODING_AGENT
            mode = assessment.execution_mode.value

        return self._response(
            request,
            descriptor,
            assessment,
            action=action,
            reason=reason,
            status=status,
            target=target,
            mode=mode,
            elapsed_ms=elapsed_ms,
            evidence_ids=result.evidence_message_ids,
            probability=result.delegation_probability,
            calibration_id=result.calibration_id,
        )

    def _unknown(
        self,
        request: DecisionRequest,
        descriptor: BackendDescriptor,
        assessment: Assessment,
        reason: ReasonCode,
        elapsed_ms: float,
    ) -> DecisionResponse:
        return self._response(
            request,
            descriptor,
            assessment,
            action=Action.ABSTAIN,
            reason=reason,
            status=DecisionStatus.UNKNOWN,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _assessment_is_consistent(assessment: Assessment) -> bool:
        return (
            assessment.task_kind is TaskKind.REPOSITORY_INSPECTION
            and assessment.execution_mode is ExecutionMode.INSPECT
        ) or (
            assessment.task_kind is TaskKind.REPOSITORY_CHANGE
            and assessment.execution_mode is ExecutionMode.MODIFY
        )

    @staticmethod
    def _available_evidence_ids(context: DecisionContext) -> set[str]:
        ids = {context.current_message.message_id}
        ids.update(message.message_id for message in context.history)
        if context.proposal is not None:
            ids.update(context.proposal.message_ids)
        return ids

    @staticmethod
    def _response(
        request: DecisionRequest,
        descriptor: BackendDescriptor,
        assessment: Assessment,
        *,
        action: Action,
        reason: ReasonCode,
        elapsed_ms: float,
        status: DecisionStatus = DecisionStatus.DECIDED,
        target: Target = Target.NONE,
        mode: str = "none",
        evidence_ids: tuple[str, ...] = (),
        probability: float | None = None,
        calibration_id: str | None = None,
    ) -> DecisionResponse:
        return DecisionResponse(
            schema_version="0.1",
            request_id=request.request_id,
            context_digest=request.context_digest,
            status=status,
            assessment=assessment,
            recommendation={"action": action, "target": target, "mode": mode},
            delegation_probability=probability,
            calibration_id=calibration_id,
            reason_codes=[reason],
            evidence_message_ids=list(evidence_ids),
            versions=descriptor.versions(POLICY_VERSION),
            elapsed_ms=elapsed_ms,
        )
