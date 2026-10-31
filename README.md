# Alcor

Alcor 是独立决策引擎：根据宿主提供的可信会话结构与有界上下文，识别用户是否要求实际执行任务，向宿主建议聊天、澄清或委派外部 Agent。首个使用场景是 Stella → Cometa → Codex 的自然语言委派。

**当前实现到 P01：协议类型、RulesBackend、本地 API 与轻量 client。模型推理、Stella 集成和任何宿主执行准入仍未实现。**

## 阅读入口

- [工程实施方案](docs/plans/2026-10-31-alcor-engineering-plan.md)：范围、架构、接入位置、任务拆解和发布门禁。
- [决策协议 v0.1](docs/contracts/decision-v0.1.md)：输入输出、语义、信任边界及宿主映射。
- [数据与评测方案](docs/evaluation/data-and-evaluation.md)：人工金标、教师合成、训练、校准与上线判据。
- [Runtime 稳定性工作包](docs/plans/runtime-reliability.md)：独立处理 llama.cpp 的健康与恢复问题。
- [讨论及源码核对](docs/research/2026-10-31-source-review.md)：需求来源、Stella 快照和讨论中需要修正的假设。
- [Laya 可行性核查](docs/research/2026-10-31-laya-feasibility.md)：上游源码、模型与训练约束。
- [进度与续接](progress.md)、[可跟踪任务](feature_list.json)。

## 本地服务

项目以 Python 3.12 为基线，依赖由 uv.lock 固定。启动本地服务：

~~~powershell
uv sync --locked --extra server
uv run --locked --extra server uvicorn alcor.api:app --host 127.0.0.1 --port 8085
~~~

服务提供 POST /v1/decisions、GET /health/live、GET /health/ready 和
GET /v1/metadata。API 默认使用规则后端。规则建议没有校准概率；响应只表达 Alcor 的语义建议，不是执行授权。Stella、Cometa 或 Codex 尚未连接到此服务。除非另行实现认证与加密，服务应保持 loopback 监听。

Python client 是异步的：

~~~python
async with AlcorClient("http://127.0.0.1:8085") as client:
    response = await client.decide(request)
~~~

AlcorClient 来自 alcor.client。client 对超时、网络故障、非法响应和 request/context 不匹配均抛出错误；调用方必须 fail closed，不能把错误当作委派建议。

## 设计资产与验证

schemas/decision-request.schema.json、schemas/decision-response.schema.json 为 JSON Schema Draft 2020-12 草案。examples/ 提供一个完整请求及对应建议响应；这些示例不是模型输出，也不是训练金标。

~~~powershell
uv run --locked python scripts/check_design_assets.py
uv run --locked ruff check src tests
uv run --locked pytest
~~~

设计资产检查验证 schema、示例、任务状态及本地文档链接。P01 契约测试验证 API、client、规则基线、隔离和故障行为。它们不能证明 Laya 模型质量、Stella 集成、只读沙盒或真实 QQ 投递。

## 后续工作

P02 冻结标签并完成人工裁决集。取得 P02 数据前不进入 Laya 对照、合成数据或微调。P06/P07 宿主集成、只读 profile、回投和灰度需要各自的证据与准入，不能由 P01 单测替代。

项目名取当前目录名 Alcor；独立发布许可证与模型分发方式在实际发布前确定。
