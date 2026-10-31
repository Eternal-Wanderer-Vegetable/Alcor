"""Conservative, deterministic baseline backend for protocol development."""

from __future__ import annotations

import re
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from alcor.backends.base import BackendDescriptor, BackendHealth, BackendResult
from alcor.contracts import (
    Assessment,
    DecisionContext,
    ExecutionMode,
    Intent,
    ReferenceStatus,
    RequestRelation,
    TaskKind,
)

_QUOTE_OR_HYPOTHETICAL = re.compile(
    r"(有人(?:说|让你|要求)|别人(?:说|要求)|假设|如果.{0,20}(?:重写|删除|修改)|"
    r"what if|hypothetically|someone asked)",
    re.IGNORECASE,
)
_DISCUSSION = re.compile(
    r"(我们可以怎么|可以怎么(?:设计|重构|处理)|如何(?:设计|理解|做)|怎么(?:理解|看待)|"
    r"讨论|建议|你怎么看|利弊|应该(?:如何|怎么)|what do you think|how should we)",
    re.IGNORECASE,
)
_CODE_SAMPLE = re.compile(
    r"(代码示例|代码样例|写.{0,8}(?:函数|例子|示例)|给我.{0,8}(?:示例|例子)|"
    r"举个例子|code example|sample function)",
    re.IGNORECASE,
)
_RESEARCH = re.compile(
    r"(联网|网上(?:搜索|查找|搜)|搜集(?:资料|信息)|调研|最新(?:信息|资料)|"
    r"web search|internet research|research this)",
    re.IGNORECASE,
)
_REPOSITORY = re.compile(
    r"(\b(?:repo|repository|codebase|project)\b|仓库|代码库|项目|源码|目录|文件|模块|"
    r"\.[a-z0-9]{1,8}\b)",
    re.IGNORECASE,
)
_CHANGE = re.compile(
    r"(\b(?:implement|fix|add|remove|refactor|modify|update|create|rewrite|edit)\b|"
    r"实现|修复|添加|删除|重构|修改|改造|改一下|改动|更新|创建|编写|重写|提交)",
    re.IGNORECASE,
)
_INSPECT = re.compile(
    r"(\b(?:inspect|investigate|diagnose|examine|search|review|analyze|test)\b|"
    r"查一下|查找|检查|调查|定位|分析|检索|测试|排查)",
    re.IGNORECASE,
)
_NO_CHANGE = re.compile(
    r"(不要(?:改|修改|编辑)|不(?:要)?改(?:动|文件|代码)?|只读|仅(?:调查|检查|分析)|"
    r"只(?:调查|检查|分析)|no changes|do not (?:edit|modify)|don't (?:edit|modify))",
    re.IGNORECASE,
)
_VAGUE_REFERENCE = re.compile(
    r"(刚才(?:那个|的)?方案|按(?:照)?(?:刚才|上面|以上|这个)|照(?:着)?(?:做|办)|"
    r"前面(?:的)?方案|the (?:previous|above) plan|do that)",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _rules_bundle_digest() -> str:
    package_root = Path(__file__).resolve().parents[1]
    paths = (
        package_root / "backends" / "base.py",
        package_root / "backends" / "rules.py",
        package_root / "contracts.py",
        package_root / "policy.py",
    )
    digest = sha256()
    for path in paths:
        digest.update(path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class RulesBackend:
    """Small transparent rule baseline; it is not a calibrated model."""

    def describe(self) -> BackendDescriptor:
        return BackendDescriptor(
            backend="rules",
            model="none",
            template="rules-v0.1",
            normalizer="context-v0.1",
            bundle="rules-v0.1",
            bundle_digest=_rules_bundle_digest(),
        )

    async def decide(
        self,
        context: DecisionContext,
        *,
        deadline_monotonic: float,
    ) -> BackendResult:
        del deadline_monotonic
        message = context.current_message
        text = " ".join(message.text.split())
        proposal_scope = context.proposal.scope if context.proposal is not None else ""
        task_text = f"{text} {proposal_scope}".strip()
        evidence = (message.message_id,)

        if message.source_kind.value == "quoted" or _QUOTE_OR_HYPOTHETICAL.search(text):
            relation = (
                RequestRelation.HYPOTHETICAL
                if _QUOTE_OR_HYPOTHETICAL.search(text)
                else RequestRelation.QUOTATION
            )
            return self._result(
                Intent.DISCUSS,
                TaskKind.UNKNOWN,
                ExecutionMode.NONE,
                ReferenceStatus.COMPLETE,
                relation,
                evidence,
            )

        if _DISCUSSION.search(text):
            task_kind = (
                TaskKind.REPOSITORY_CHANGE if _REPOSITORY.search(text) else TaskKind.KNOWLEDGE
            )
            return self._result(
                Intent.DISCUSS,
                task_kind,
                ExecutionMode.NONE,
                ReferenceStatus.COMPLETE,
                RequestRelation.SELF_REQUEST,
                evidence,
            )

        if _CODE_SAMPLE.search(text):
            return self._result(
                Intent.CHAT,
                TaskKind.CODE_SAMPLE,
                ExecutionMode.NONE,
                ReferenceStatus.COMPLETE,
                RequestRelation.SELF_REQUEST,
                evidence,
            )

        if _RESEARCH.search(text):
            return self._result(
                Intent.EXECUTE,
                TaskKind.RESEARCH,
                ExecutionMode.UNKNOWN,
                ReferenceStatus.COMPLETE,
                RequestRelation.SELF_REQUEST,
                evidence,
            )

        has_repository = bool(_REPOSITORY.search(task_text))
        wants_change = bool(_CHANGE.search(text) or _CHANGE.search(proposal_scope))
        wants_inspection = bool(_INSPECT.search(text) or _INSPECT.search(proposal_scope))
        no_change = bool(_NO_CHANGE.search(text))

        references_plan = bool(_VAGUE_REFERENCE.search(text) and context.proposal is not None)
        if has_repository and (wants_change or wants_inspection or references_plan):
            mode = (
                ExecutionMode.INSPECT
                if no_change or (wants_inspection and not wants_change)
                else ExecutionMode.MODIFY
                if wants_change
                else ExecutionMode.INSPECT
            )
            task_kind = (
                TaskKind.REPOSITORY_INSPECTION
                if mode is ExecutionMode.INSPECT
                else TaskKind.REPOSITORY_CHANGE
            )
            reference = (
                ReferenceStatus.MISSING
                if _VAGUE_REFERENCE.search(text) and context.proposal is None
                else ReferenceStatus.COMPLETE
            )
            return self._result(
                Intent.EXECUTE,
                task_kind,
                mode,
                reference,
                RequestRelation.SELF_REQUEST,
                evidence,
            )

        if _VAGUE_REFERENCE.search(text):
            return self._result(
                Intent.EXECUTE,
                TaskKind.UNKNOWN,
                ExecutionMode.UNKNOWN,
                ReferenceStatus.MISSING,
                RequestRelation.SELF_REQUEST,
                evidence,
            )

        if wants_change or wants_inspection:
            if wants_change and not has_repository and _CODE_SAMPLE.search(text):
                return self._result(
                    Intent.CHAT,
                    TaskKind.CODE_SAMPLE,
                    ExecutionMode.NONE,
                    ReferenceStatus.COMPLETE,
                    RequestRelation.SELF_REQUEST,
                    evidence,
                )
            return self._result(
                Intent.EXECUTE,
                TaskKind.REPOSITORY_INSPECTION if not wants_change else TaskKind.REPOSITORY_CHANGE,
                ExecutionMode.INSPECT if no_change or not wants_change else ExecutionMode.MODIFY,
                ReferenceStatus.MISSING,
                RequestRelation.SELF_REQUEST,
                evidence,
            )

        return self._result(
            Intent.CHAT,
            TaskKind.KNOWLEDGE,
            ExecutionMode.NONE,
            ReferenceStatus.COMPLETE,
            RequestRelation.SELF_REQUEST,
            evidence,
        )

    async def health(self) -> BackendHealth:
        return BackendHealth(ready=True, backend="rules")

    @staticmethod
    def _result(
        intent: Intent,
        task_kind: TaskKind,
        execution_mode: ExecutionMode,
        reference_status: ReferenceStatus,
        request_relation: RequestRelation,
        evidence: tuple[str, ...],
    ) -> BackendResult:
        return BackendResult(
            assessment=Assessment(
                intent=intent,
                task_kind=task_kind,
                execution_mode=execution_mode,
                reference_status=reference_status,
                request_relation=request_relation,
            ),
            evidence_message_ids=evidence,
        )
