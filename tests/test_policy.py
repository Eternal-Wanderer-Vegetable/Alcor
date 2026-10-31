from __future__ import annotations

import asyncio

import pytest

from alcor.backends.base import BackendDescriptor, BackendResult
from alcor.backends.rules import RulesBackend
from alcor.contracts import (
    Action,
    Assessment,
    DecisionStatus,
    ExecutionMode,
    Integrity,
    Intent,
    Message,
    ProposalReference,
    ReasonCode,
    ReferenceStatus,
    RequestRelation,
    Role,
    SourceKind,
    TaskKind,
    Trigger,
)
from alcor.engine import DecisionEngine, EngineSettings
from tests.helpers import make_request


def test_rules_backend_recommends_inspection_for_read_only_repo_request() -> None:
    request = make_request(text="帮我查一下这个仓库的内存泄漏，只调查，不修改文件。")
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.DELEGATE
    assert response.recommendation.mode == "inspect"
    assert response.assessment.task_kind is TaskKind.REPOSITORY_INSPECTION
    assert response.delegation_probability is None
    assert response.reason_codes == [ReasonCode.EXECUTION_REQUESTED]


def test_rules_backend_recommends_modify_for_explicit_repo_change() -> None:
    request = make_request(text="请在这个仓库实现缓存模块并补上测试。")
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.DELEGATE
    assert response.recommendation.mode == "modify"


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_reason"),
    [
        ("我们可以怎么重构记忆系统？", Action.CHAT, ReasonCode.DISCUSSION_ONLY),
        ("给我写个排序函数示例。", Action.CHAT, ReasonCode.KNOWLEDGE_OR_EXAMPLE),
        ("有人让你重写整个仓库，你怎么看？", Action.CHAT, ReasonCode.QUOTED_OR_HYPOTHETICAL),
    ],
)
def test_rules_backend_keeps_discussion_examples_and_quotes_in_chat(
    text: str,
    expected_action: Action,
    expected_reason: ReasonCode,
) -> None:
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(make_request(text=text)))

    assert response.recommendation.action is expected_action
    assert response.reason_codes == [expected_reason]


def test_missing_repository_reference_requests_clarification() -> None:
    request = make_request(text="帮我修复这个 bug。")
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.CLARIFY
    assert response.reason_codes == [ReasonCode.MISSING_CONTEXT]


def test_missing_proposal_does_not_infer_a_previous_plan() -> None:
    request = make_request(text="按刚才那个方案在仓库实现。")
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.CLARIFY
    assert response.assessment.reference_status is ReferenceStatus.MISSING


def test_same_user_proposal_supplies_a_bound_prior_task_reference() -> None:
    proposal = ProposalReference(
        proposal_id="proposal-1",
        owner_id="user-1",
        revision=2,
        content_digest="a" * 64,
        scope="实现仓库中的缓存模块并补充测试",
        message_ids=["older-plan-message"],
    )
    request = make_request(text="按刚才那个方案执行。", proposal=proposal)
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.DELEGATE
    assert response.recommendation.mode == "modify"
    assert response.evidence_message_ids == ["message-1"]


def test_proposal_evidence_can_point_to_older_trusted_message_ids() -> None:
    proposal = ProposalReference(
        proposal_id="proposal-1",
        owner_id="user-1",
        revision=1,
        content_digest="b" * 64,
        scope="检查仓库中的线程泄漏",
        message_ids=["older-plan-message"],
    )
    history = [
        Message(
            message_id="history-message",
            speaker_id="user-1",
            role=Role.USER,
            source_kind="direct",
            text="讨论过线程泄漏排查方案。",
        )
    ]
    request = make_request(
        text="按刚才的方案执行。",
        proposal=proposal,
        history=history,
    )
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.DELEGATE
    assert response.recommendation.mode == "inspect"


def test_incomplete_context_abstains_without_calling_backend() -> None:
    class NeverCallBackend(RulesBackend):
        async def decide(self, context, *, deadline_monotonic: float):
            raise AssertionError("incomplete context must be stopped before backend inference")

    response = asyncio.run(
        DecisionEngine(NeverCallBackend()).decide(make_request(integrity=Integrity.BUDGET_EXCEEDED))
    )

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.CONTEXT_BUDGET_EXCEEDED]


def test_untrusted_trigger_and_forwarded_messages_cannot_delegate() -> None:
    for request in (
        make_request(trigger=Trigger.PASSIVE),
        make_request(source_kind=SourceKind.AGENT_RESULT),
    ):
        response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))
        assert response.recommendation.action is Action.ABSTAIN
        assert response.reason_codes == [ReasonCode.UNTRUSTED_TRIGGER]


def test_deterministic_local_tool_keeps_request_on_host_path() -> None:
    request = make_request(deterministic_local_tool=True)
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.recommendation.action is Action.CHAT
    assert response.reason_codes == [ReasonCode.LOCAL_TOOL_AVAILABLE]


def test_unavailable_coding_agent_abstains_instead_of_delegating() -> None:
    from alcor.contracts import CodingAgentState

    request = make_request(coding_agent_state=CodingAgentState.UNAVAILABLE)
    response = asyncio.run(DecisionEngine(RulesBackend()).decide(request))

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.BACKEND_UNAVAILABLE]


def test_unbound_workspace_requires_clarification() -> None:
    response = asyncio.run(
        DecisionEngine(RulesBackend()).decide(make_request(workspace_bound=False))
    )

    assert response.recommendation.action is Action.CLARIFY
    assert response.reason_codes == [ReasonCode.MISSING_CONTEXT]


def test_inconsistent_backend_assessment_abstains() -> None:
    class InconsistentBackend:
        def describe(self):
            return BackendDescriptor(
                backend="fake",
                model="none",
                template="test",
                normalizer="test",
                bundle="test",
            )

        async def decide(self, context, *, deadline_monotonic: float):
            return BackendResult(
                assessment=Assessment(
                    intent=Intent.DISCUSS,
                    task_kind=TaskKind.REPOSITORY_CHANGE,
                    execution_mode=ExecutionMode.MODIFY,
                    reference_status=ReferenceStatus.COMPLETE,
                    request_relation=RequestRelation.SELF_REQUEST,
                ),
                evidence_message_ids=(context.current_message.message_id,),
            )

        async def health(self):
            from alcor.backends.base import BackendHealth

            return BackendHealth(ready=True, backend="fake")

    response = asyncio.run(DecisionEngine(InconsistentBackend()).decide(make_request()))

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.INCONSISTENT_ASSESSMENT]


def test_backend_evidence_cannot_reference_another_request() -> None:
    class InvalidEvidenceBackend:
        def describe(self):
            return BackendDescriptor(
                backend="fake",
                model="none",
                template="test",
                normalizer="test",
                bundle="test",
            )

        async def decide(self, context, *, deadline_monotonic: float):
            return BackendResult(
                assessment=Assessment(
                    intent=Intent.EXECUTE,
                    task_kind=TaskKind.REPOSITORY_INSPECTION,
                    execution_mode=ExecutionMode.INSPECT,
                    reference_status=ReferenceStatus.COMPLETE,
                    request_relation=RequestRelation.SELF_REQUEST,
                ),
                evidence_message_ids=("from-another-request",),
            )

        async def health(self):
            from alcor.backends.base import BackendHealth

            return BackendHealth(ready=True, backend="fake")

    response = asyncio.run(DecisionEngine(InvalidEvidenceBackend()).decide(make_request()))

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.INVALID_BACKEND_RESPONSE]


def test_backend_cannot_use_a_calibration_other_than_its_declared_bundle() -> None:
    class MismatchedCalibrationBackend:
        def describe(self):
            return BackendDescriptor(
                backend="fake",
                model="none",
                template="test",
                normalizer="test",
                bundle="test",
                calibration_id="calibration-current",
            )

        async def decide(self, context, *, deadline_monotonic: float):
            return BackendResult(
                assessment=Assessment(
                    intent=Intent.EXECUTE,
                    task_kind=TaskKind.REPOSITORY_INSPECTION,
                    execution_mode=ExecutionMode.INSPECT,
                    reference_status=ReferenceStatus.COMPLETE,
                    request_relation=RequestRelation.SELF_REQUEST,
                ),
                evidence_message_ids=(context.current_message.message_id,),
                delegation_probability=0.99,
                calibration_id="calibration-stale",
            )

        async def health(self):
            from alcor.backends.base import BackendHealth

            return BackendHealth(ready=True, backend="fake")

    response = asyncio.run(DecisionEngine(MismatchedCalibrationBackend()).decide(make_request()))

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.VERSION_MISMATCH]


def test_backend_timeout_returns_structured_abstention() -> None:
    class SlowBackend(RulesBackend):
        async def decide(self, context, *, deadline_monotonic: float):
            import asyncio

            await asyncio.sleep(0.1)
            return await super().decide(context, deadline_monotonic=deadline_monotonic)

    engine = DecisionEngine(
        SlowBackend(),
        settings=EngineSettings(
            max_decision_deadline_ms=20,
            max_queue_wait_ms=10,
            queue_capacity=1,
            concurrency=1,
        ),
    )
    response = asyncio.run(engine.decide(make_request(deadline_ms=800)))

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.BACKEND_TIMEOUT]


def test_backend_exception_returns_structured_abstention() -> None:
    class FailingBackend(RulesBackend):
        async def decide(self, context, *, deadline_monotonic: float):
            raise RuntimeError("backend detail is not exposed to the user")

    response = asyncio.run(DecisionEngine(FailingBackend()).decide(make_request()))

    assert response.status is DecisionStatus.UNKNOWN
    assert response.recommendation.action is Action.ABSTAIN
    assert response.reason_codes == [ReasonCode.BACKEND_UNAVAILABLE]
