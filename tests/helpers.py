from __future__ import annotations

from alcor.contracts import (
    CodingAgentState,
    DecisionContext,
    DecisionRequest,
    HostFacts,
    Integrity,
    Message,
    ProposalReference,
    Role,
    SourceKind,
    Trigger,
    context_digest,
)


def make_request(
    *,
    request_id: str = "request-1",
    message_id: str = "message-1",
    text: str = "在这个仓库检查并修复内存泄漏。",
    deadline_ms: int = 800,
    role: Role = Role.USER,
    source_kind: SourceKind = SourceKind.DIRECT,
    trigger: Trigger = Trigger.REPLY,
    workspace_bound: bool = True,
    coding_agent_state: CodingAgentState = CodingAgentState.READY,
    deterministic_local_tool: bool = False,
    integrity: Integrity = Integrity.COMPLETE,
    history: list[Message] | None = None,
    proposal: ProposalReference | None = None,
) -> DecisionRequest:
    context = DecisionContext(
        current_message=Message(
            message_id=message_id,
            speaker_id="user-1",
            role=role,
            source_kind=source_kind,
            text=text,
        ),
        history=history or [],
        proposal=proposal,
        integrity=integrity,
        host_facts=HostFacts(
            trigger=trigger,
            workspace_bound=workspace_bound,
            coding_agent_state=coding_agent_state,
            deterministic_local_tool=deterministic_local_tool,
        ),
    )
    return DecisionRequest(
        schema_version="0.1",
        request_id=request_id,
        context_digest=context_digest(context),
        deadline_ms=deadline_ms,
        context=context,
    )
