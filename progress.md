# Alcor 进度与续接

更新：2026-10-31（Asia/Shanghai）。

## 本轮范围与结果

按工程方案完成 P01：建立轻量 Python 服务、严格协议类型、RulesBackend、策略组合、API 与异步 client。没有安装 torch、下载模型权重，也没有改动 Stella 工作区。

P00 设计资产在本轮开始时提交为基线 `b18c62a`（`docs: establish Alcor P00 design baseline`）。本地分支为 `codex/alcor-p01-decision-api`。P01 阶段提交与验证证据见 Git 历史及 [P01 验证记录](evidence/p01-validation.txt)。

## P01 交付

- `pyproject.toml`、`uv.lock`、`.python-version`：Python 3.12 工程及跨平台锁定依赖。
- `src/alcor/contracts.py`：严格请求/响应、规范化上下文摘要、proposal 同用户绑定和跨字段约束。
- `src/alcor/backends/`、`src/alcor/policy.py`：未校准的规则基线与保守宿主事实组合。
- `src/alcor/engine.py`：共享 deadline、单并发 worker、有界队列，以及 timeout/busy/backend failure 的 abstain 结果。
- `src/alcor/api.py`、`src/alcor/client.py`：Decision API、健康/metadata 端点、body 限制和请求/响应绑定 client。
- `tests/`：fake backend、API、client、跨请求隔离、JSON/schema 边界和故障契约覆盖。

规则 backend 没有校准概率；API 的 delegate 只是语义建议，不能授权或提交任务。没有接入 Stella、Cometa、Codex 或 QQ。

## 验证范围

Windows Python 3.12 与 WSL Ubuntu Python 3.12 均运行 P01 契约测试、Ruff 和设计资产检查。详细命令、版本、测试数及最初暴露并修复的 WSL 盘符链接问题记录在 `evidence/p01-validation.txt`。

设计资产检查只验证 schema、示例、任务状态和本地链接；P01 测试只证明当前 API/client 与 RulesBackend 契约，不证明真实模型或平台运行质量。

## 尚未完成的工作

- P02 仍需人工裁决 500 个案例及锁定 family split；不得用模型生成标签代替裁决。
- P03 需 P02 数据及固定 Laya checkpoint 后才能做零样本对照与 CPU/长度实测。
- P04/P05 合成数据、训练、校准与发布 bundle 尚未开始。
- P06/P07 Stella shadow、真实只读 profile、sandbox、幂等恢复和 QQ/WebChat 回投尚未实现或验收。
- P08 仍受审批与写入授权链缺失限制。R01/R02 Runtime 诊断与恢复未运行。

## 恢复工作时先读

先读 [工程实施方案](docs/plans/2026-10-31-alcor-engineering-plan.md)、[协议](docs/contracts/decision-v0.1.md)、[数据与评测方案](docs/evaluation/data-and-evaluation.md)、[可跟踪任务](feature_list.json)。下一阶段是 P02 的人工标注与 split 冻结；P01 API 不能替代后续离线模型、宿主准入或实地验收。
