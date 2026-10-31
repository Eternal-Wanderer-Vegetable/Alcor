# Alcor

Alcor 是拟建设的独立决策引擎：根据宿主提供的可信会话结构与有界上下文，识别用户是否要求实际执行任务，向宿主建议聊天、澄清或委派外部 Agent。首个使用场景是 Stella → Cometa → Codex 的自然语言委派。

**当前交付是工程方案、协议草案和验收资产；服务、模型与 Stella 集成都尚未实现。**

## 阅读入口

- [工程实施方案](docs/plans/2026-10-31-alcor-engineering-plan.md)：范围、架构、接入位置、任务拆解和发布门禁。
- [决策协议 v0.1](docs/contracts/decision-v0.1.md)：输入输出、语义、信任边界及宿主映射。
- [数据与评测方案](docs/evaluation/data-and-evaluation.md)：人工金标、教师合成、训练、校准与上线判据。
- [Runtime 稳定性工作包](docs/plans/runtime-reliability.md)：独立处理 llama.cpp 的健康与恢复问题。
- [讨论及源码核对](docs/research/2026-10-31-source-review.md)：需求来源、Stella 快照和讨论中需要修正的假设。
- [Laya 可行性核查](docs/research/2026-10-31-laya-feasibility.md)：上游源码、模型与训练约束。
- [进度与续接](progress.md)、[可跟踪任务](feature_list.json)。

## 可检查的设计资产

`schemas/decision-request.schema.json`、`schemas/decision-response.schema.json` 为 JSON Schema Draft 2020-12 草案。`examples/` 提供一个完整请求及对应建议响应。这些示例不是实际模型输出，也不是训练金标。

当前可执行的检查仅覆盖设计资产：

```powershell
python scripts/check_design_assets.py
```

需要本机 Python 和 `jsonschema`。该检查验证 schema、示例、任务状态及本地文档链接，不能证明模型效果或产品运行质量。

## 第一轮实施范围

先完成协议冻结、人工裁决集和规则/Laya 零样本对照。只有离线证据支持时才投入微调；只有宿主准入与故障行为通过时才进入只读灰度。8192 tokens 上限继续适用于 Stella 主聊天及 Compact 完整单元批处理；Alcor 另设模型实际 tokenizer 预算。

项目名取当前目录名 Alcor；独立发布许可证与模型分发方式在实际发布前确定。
