# 讨论与 Stella 源码核对

日期：2026-10-31。只读范围：分享讨论、指定源码及GitNexus索引；未读生产聊天库、未调用真实Codex、未操作模型或托管服务。

## 需求来源

[用户提供的讨论](https://chatgpt.com/share/6ae522dc-0780-83e8-af92-c16e7a04746e)，页面标题“自然调用Codex研究”。Web文本抓取仅得到标题；通过浏览器读取公开页面渲染正文，完整看到三轮讨论。没有将页面里的“可以继续做什么”当作额外授权。

讨论依次考察现有自动委派、主模型唯一工具、独立外部决策模型；最终用户选择第三条，并要求独立子项目、大模型合成数据加人工判断及连接稳定性。本方案据此收敛；研究项目/论文的性能数字不作为Alcor预期收益，不必复现全部研究才可启动工程。

## 本地证据边界

Alcor开始时为空目录且不是Git仓库。本轮未初始化Git或创建远程仓库。Stella基线HEAD为`cf630612c05f8ff9f7c8c61192b060c77b676856`；当前已有未提交修改，未覆盖。引用以本轮实际源文件hash为准，详见[source snapshot](../../evidence/source-snapshot.json)。

GitNexus Docker `stella-gitnexus` list 查询12秒超时，未重启服务。WSL备用runner使用1.6.12，`list`返回3个仓库记录，其中两个同名Stella。所有后续查询明确绑定`--repo /mnt/e/stella/stella_project`，索引HEAD与当前一致，indexedAt=`2026-10-29T10:31:12.540Z`。该索引位于`/home/vegetable/.cache/gitnexus-stella-workspace/stella_project-db25a9fbfbfd`。

Windows项目内`.gitnexus/meta.json`指向旧`/repo`、commit `fcbf91e...`，没有用该快照证明当前调用关系。当前HEAD对齐也不能覆盖未提交源码变化；所引用路径逐个读取并保存hash，不把图当唯一证据。

已运行图查询：

```text
gitnexus list
gitnexus query "Cometa delegation decide_auto activate_capabilities" --repo /mnt/e/stella/stella_project
gitnexus context decide_auto --repo /mnt/e/stella/stella_project
gitnexus context handle_delegation_turn --repo /mnt/e/stella/stella_project
gitnexus query "llama embedding health runtime" --repo /mnt/e/stella/stella_project
```

`decide_auto`的生产调用者是`decide`；`handle_delegation_turn`的生产调用者是`activate_capabilities`。这些context返回processes为空，不能解释成没有执行路径；源码确认钩子通过`pipeline.register_pre_hook(... priority=HOOK_PRIORITY)`注册。未编辑Stella符号，所以本轮没有执行编辑影响门禁或提交detect_changes；真正集成时须重新执行。

## 源码对照

| 已核实事实 | 当前定位 | 工程影响 |
| --- | --- | --- |
| 自动委派是关键词/长度/现有route组合 | [delegation.py](/E:/stella/stella_project/capability/delegation.py:138) | 可作为既有基线，不能直接证明跨轮语义 |
| 显式命令优先 | [decide](/E:/stella/stella_project/capability/delegation.py:157) | Alcor不劫持任务控制命令 |
| 委派处理在Comes/Skills前 | [hooks.py](/E:/stella/stella_project/capability/hooks.py:415) | 接管后避免同目标重复执行 |
| 委派短事务与错误兜底 | [handle](/E:/stella/stella_project/capability/delegation.py:236) | 不把Agent长任务放聊天deadline里等待 |
| TaskSpec有上下文、profile、workspace | [TaskSpec](/E:/stella/stella_project/cometa/models.py:478) | 补可信映射即可，不需重造任务存储 |
| 当前提交主要传objective/backend | [submit helper](/E:/stella/stella_project/capability/delegation.py:318) | 自然引用及只读映射不能自动继承 |
| 策略核验白名单与profile/workspace/backend | [policy.py](/E:/stella/stella_project/cometa/policy.py:38) | Alcor建议仍经过既有准入 |
| 默认profile可能可写 | [ProfileConfig](/E:/stella/stella_project/cometa/config.py:222) | inspect必须显式映射只读profile |
| submit校验身份、持久化与幂等 | [service.py](/E:/stella/stella_project/cometa/service.py:128) | accepted不等于running/completed |
| Codex人工审批关闭，sandbox按profile设置 | [codex.py](/E:/stella/stella_project/cometa/backends/codex.py:104) | 不声称已有人工approval闭环 |
| 内置llama以embedding参数启动 | [llama launch](/E:/stella/stella_project/deploy/llama.py:127) | 独立诊断实际端点，不归因于路由模型 |
| 端点ready仅GET模型列表 | [endpoint_ready](/E:/stella/stella_project/deploy/llama.py:32) | 新增inference-ready证据 |
| runtime默认组件stella/llama/onebot | [manifest](/E:/stella/stella_project/deploy/runtime.py:94) | 正式托管Alcor需新增组件合同，不能冒充embedding |
| 预算器保留8192工作窗口及身份保护 | [context_budget](/E:/stella/stella_project/core/context_budget.py:1) | 保持窗口，有界结果及独立决策预算 |

本文件的本机源码链接只用于本机跳转；可迁移证据以source snapshot中的relative path、HEAD及hash为准。

## 讨论中需要纠正或加条件的假设

1. 独立决策层提升可替换性与可测性，但不自动修复llama.cpp断连；必须有独立Runtime诊断与恢复证据。
2. “相同体验”应约束为相同标准化输入下相同前置判断；不同聊天模型生成不同历史时不能承诺完全相同结果。
3. 用户说“按方案做”要求引用绑定。现有helper只传当前objective，不能依靠关键词或模型自由补齐方案。
4. Laya官方服务、训练器和校准入口存在，但multilingual默认未校准，弃权标志不会替宿主拦截执行；问题数量也不是零成本。详见[Laya研究](2026-10-31-laya-feasibility.md)。
5. 原分享中建议输出`requires_approval=false`容易被误当权限事实，本协议把授权状态留给宿主，不由模型作最终断言。
6. 当前Codex适配器不具备人工审批闭环；分阶段首推只读，写入由可信范围授权与真实后端能力决定。

## Codex 官方能力核对

OpenAI Docs将`codex exec`定位为非交互任务，SDK用于程序化工作流，App Server用于持续会话、流式事件和审批处理；这是上游可用接入面的说明，不能证明Stella适配器实现了所有能力。[Codex as a platform](https://developers.openai.com/blog/codex-as-a-platform)

官方App Server支持stdio JSONL及线程/轮次生命周期，审批通过服务端发起请求与客户端回复完成。Alcor沿用现有Cometa适配器；若以后需要人工审批或恢复重放，必须实现并验证宿主桥接，不能只改capability标志。[官方App Server文档](https://learn.chatgpt.com/docs/app-server)

## 既有历史的使用

曾有Stella内置Laya级联计划，提供“可替换DecisionBackend、语义不等于授权、独立worker、保留unknown和部署合同”的历史约束。本轮重新检查当前源代码和上游；旧计划的模型版本、图索引和90项旧测试成绩均不作为当前验收。当前独立Alcor/Codex首期范围优先于旧的全工具候选核验范围。
