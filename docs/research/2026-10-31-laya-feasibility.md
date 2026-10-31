# Laya 候选决策后端可行性核查

访问日期：2026-10-31（Asia/Shanghai）。性质：一手文档、GitHub 源码及 Hugging Face 元数据核查。没有安装依赖、下载模型权重、启动服务、训练或执行推理；所有性能、质量和平台表现均不是 Alcor 本机验收结果。

## 结论与工程取舍

Laya 可进入 Alcor 的独立外部决策引擎候选适配层：它有非生成式 typed decision Python 实现及官方 HTTP 入口，能把给定状态与候选项映射到 `choice`、`score`、`noul`。这支持“受约束的决策后端”定位，不能据此推出可靠的通用推理、动作授权或中文生产可用性。建议先锁定 multilingual checkpoint、保留概率与截断元数据、外置策略门、建立本域独立评估集，然后进行 CPU/Windows 和目标硬件验收。[官方类型实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1370-L1441)、[HTTP 实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py)

最关键的限制是：multilingual 默认未拟合校准；默认序列长度 1024、可显式提高到 8192，但状态实际可用空间要扣除问题头；`min_confidence` 只添加弃权标志，调用者仍会收到原答案；严格 Jev 投影会移除 Alcor 需要的扩展字段。Alcor 必须自行执行弃权、超时、故障和证据不足时的回退策略。[模型配置](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/rl_agent_config.json)、[序列构造](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/common.py#L157-L218)、[弃权实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/confidence.py#L265-L341)、[严格投影](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py#L222-L262)

## 1. 官方身份与可重现源快照

以相互链接的 `NandhaKishorM/laya`、PyPI 包名 `laya`、作者 Convai Innovations 和 `convaiinnovations/*` 模型仓库为本次上游身份。其他所有者的同名 fork、另一个名为 LAYA 的论文、社区容器或 native runtime 均不替代此身份。[包元数据](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/pyproject.toml)、[官方模型卡反向链接](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/README.md)

| 对象 | 此次解析结果 | 一手定位 |
| --- | --- | --- |
| 官方 GitHub main | `118d361a774c9a28cd02a78d6cf4d2af0614f422`，committer 时间 `2026-10-30T07:39:50Z` | [GitHub commit API](https://api.github.com/repos/NandhaKishorM/laya/commits/118d361a774c9a28cd02a78d6cf4d2af0614f422) |
| 该源码声明版本 | `0.4.18`，Python `>=3.10`，Apache-2.0 | [pyproject.toml](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/pyproject.toml) |
| 独立 multilingual 模型仓库 | `convaiinnovations/laya-multilingual` @ `1720e3e3357cfe1e281542e223f8273b0890ca34` | [HF API](https://huggingface.co/api/models/convaiinnovations/laya-multilingual)、[固定树](https://huggingface.co/convaiinnovations/laya-multilingual/tree/1720e3e3357cfe1e281542e223f8273b0890ca34) |
| 默认 Router 使用的 bundled 仓库 | `convaiinnovations/laya` @ `7b928d828b7b0e022f929d9bd2e44165aa270148`，multilingual 位于 `multilingual/` | [Router 默认映射](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/router.py#L50-L64)、[固定模型树](https://huggingface.co/convaiinnovations/laya/tree/7b928d828b7b0e022f929d9bd2e44165aa270148/multilingual) |

不能把独立 multilingual 仓库的 SHA 填给默认 bundled Router 并假定可用；仓库身份、subfolder 和 revision 必须一起保存。源码 `Router(revision=..., revisions=...)` 支持整体或逐模型固定，默认不主动固定；`LAYA_REVISION` 和 `LAYA_SHA256_DIGESTS` 也是 opt-in。[Router revision 规则](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/router.py#L579-L594)、[revision/digest 实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/revisions.py)

本次仅下载文本源码到临时目录进行只读检查。文本快照 SHA256：

| 固定源码文件 | SHA256 |
| --- | --- |
| `laya/agent.py` | `fe569b96e6640508599e983d6d68b41c0993c52cdc959f3f4c03ff60c4a18831` |
| `laya/common.py` | `8cb7b9530134dcd5d4392c6c13d1a3d26672a5d4d5097507a01345533a9bc52b` |
| `laya/serve.py` | `6579a2e2b6150dda85c8a9789637b73e41db692ca687fc63e5b9dee77528c0c7` |
| `laya/train.py` | `c325941f275a90b486d00c3ca28dc4ee1ece795218fdaa7c67818d711ee79645` |
| `laya/calibrate.py` | `f4dcb80c7f88d06e0e77d88b56275b11578f99f3ea6d659f6f0fdeb2df973787` |
| multilingual `rl_agent_config.json`（独立仓库与 bundle 的该文件本次哈希相同） | `25061739243b617ad88d1219ba6f8a9c86c5881ca28df024fa2d9b3b2fcc30c6` |

HF 树 API 对独立 multilingual `model.safetensors` 报告 size `643835514` bytes、LFS SHA256 `9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204`。这是**服务端元数据**，没有下载或本地校验权重，不能作为本机资产验收。[固定 revision 树 API](https://huggingface.co/api/models/convaiinnovations/laya-multilingual/tree/1720e3e3357cfe1e281542e223f8273b0890ca34?recursive=true)

## 2. multilingual 参数、输入上限与截断

官方模型卡称总参数约 322M，编码器 mmBERT-base 约 307M，加两层决策头；编码器配置核实为 hidden size 768、22 层、vocab 256000、`max_position_embeddings=8192`。这不是 0.3B 自回归聊天模型，且本次没有从权重逐项数参数。[模型卡 Architecture](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/README.md)、[encoder 配置](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/encoder/config.json)

- checkpoint `max_len=1024`、`head_max_len=256`；`predict(..., max_len=8192)` 可显式放大。8192 是总序列 token 上限，不是 8192 个中文字符，也不是纯 state 容量。[checkpoint 配置](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/rl_agent_config.json)
- 序列由 type、instructions、每个 option 的 marker/文本、分隔符及 state 共同组成。`room=max(0,max_len-len(head)-1)`；所以每个问题有自己的 state 剩余预算。head 的 option 文本也会被预算压缩，问题选项失去可区分性是另一类风险。[`build_sequence` 与 `build_head`](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/common.py#L157-L279)
- 当前 Agent 对字符串/对象 state 保留前部，丢弃超限尾部；对 conversation list 保留尾部，以保留新近 turn。这是按 token 切片，可能切在消息内部，并非完整消息级无损压缩。[Agent `truncate_left`](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1169-L1216)、[切片实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/common.py#L198-L218)
- 当前普通预测会报告 `usage.truncated`、`state_tokens`、`state_tokens_dropped`、`truncated_questions`；不能仅因 HTTP 200 或有答案便认为全量状态被读取。[预测接口契约](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1936-L1981)
- 官方提供 `predict_long` 多窗口路径，但其聚合概率不是整篇文档已校准概率：例如 noul 取最大 P(true)，窗口数增加会抬高阳性倾向；此路径没有统一 `min_confidence` 门。Alcor 不应把逐窗高置信当作全局证明。[长文预测契约与实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1649-L1738)

工程建议（本次研究推论）：先用有明确预算的特征/证据 envelope，不默认把所有会话历史扔给 Laya；输入超限应产生可审计状态并按任务选择拒绝、完整单元分批或另行抽取，不能静默切掉尚未消费的信息。8192 能被编码不意味着本域长文决策质量达标。

多问题的前向粒度需准确表述：普通 `Agent.predict/system_one` 会把同一个 state 的每个 question 分别构造成一行完整序列，再将 Q 行 collate 为一个 tensor，通常一次 `_forward` 同时计算这些行。**不是逐 question 串行 Q 次 forward，也不是只编码一次 state 后免费读出 Q 个结果**：state 的 tokenization 可复用，但每行含独立 question head 和 state，encoder 计算/显存随 Q 和实际 token 长度增长。`predict_batch` 还可把多 state 的 question 行打包，显式 batch_size、Router 分模型路由、长文分窗/分块等会带来多次 forward。延迟预算应记录 questions 数、每行长度、batch/padding、forward 次数及并发，不能用“单次前向”把多问成本视为常量。[每问题编码](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1169-L1216)、[collate/forward 主循环](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1455-L1608)

在 Alcor 首版中，以上能力只作为 Codex 自然委派链的候选判断后端；`off/shadow/readonly/admitted` 与宿主准入属于 Alcor/宿主契约，Laya 本身不实现这些模式，也不替代 embedding 或 memory。Laya 的模型门通过仍不能代替宿主决定是否执行。

## 3. 官方服务能力及健康边界

官方包 extra 是 `laya[serve]`，entry point `laya-serve = laya.serve:main`。当前源码明确包含 `POST /v1/systemone`、`POST /v1/systemone/batch`、`GET /health`。这确认源码入口存在，未证明本机安装、启动或兼容任何既有客户端。[包 entry points](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/pyproject.toml)、[路由实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py#L1345-L1512)

可用于未来独立隔离验收的 PowerShell 示例，**本次没有执行**：

```powershell
$env:LAYA_HOST = '127.0.0.1'
$env:LAYA_PORT = '8000'
$env:LAYA_DEVICE = 'cpu'
$env:LAYA_MODELS = 'multilingual'
$env:LAYA_PRELOAD = '1'
$env:LAYA_REVISION = '7b928d828b7b0e022f929d9bd2e44165aa270148' # 默认 bundle
$env:LAYA_JEV_STRICT = '0'
laya-serve
```

`LAYA_MODELS` 控制预加载集合；并不等于只允许这一模型，更不替代请求中显式 `model="multilingual"`。`LAYA_THREADS` 可限制 CPU intra-op 线程；`LAYA_MAX_CONCURRENT` 默认 16，饱和返回 503。`LAYA_API_KEY` 可启用 Bearer。默认绑定 `0.0.0.0:8000`，未来本机试验建议显式回环绑定。当前服务有 2 MiB body、64 questions、请求 token budget 默认上限 8192 等边界；这些限制与模型有效 state 预算是不同层次。[服务配置及常量](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py#L17-L177)、[预加载构造](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py#L1178-L1207)

`/health` 的 `status=ok` 是存活证据。完整响应还报告 `loaded`、`revisions`、`device`、`device_is_preference`、`checkpoint_devices`、`cpu_fallbacks`；没有 resident model 时 device 只是偏好。启用 API key 后未认证 health 只返回存活状态。应同时检验目标模型实际 loaded/revision、执行设备及真实推理探针，不能拿一次 `/health` 代替 readiness 或决策质量验收。[health 源码](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py#L1345-L1392)

`LAYA_JEV_STRICT=1` 通过白名单投影保留 Jev 字段，删除 routing、action、answer_confidence、noul confidence、abstention、abstention_threshold 及截断扩展。Alcor 应保留完整 Laya 响应或在自己的 adapter 中显式重建所需证据，不能同时开启严格投影并期待这些扩展存在。相同 wire shape 也不表示 Laya/Jev confidence 数值语义一致。[严格投影](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/serve.py#L222-L262)、[Jev confidence 对照实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/confidence.py#L62-L110)

## 4. 决策字段精确定义

| 字段 | 当前固定源码行为 | Alcor 风险/解释 |
| --- | --- | --- |
| `choice` | 按候选项 logits 经温度缩放后 softmax，返回 argmax 对应 label；附各 option 概率 | 只能在提供的候选中选择；未提供 `other/unknown` 就没有开放集识别保证 |
| `score` | 对 ordinal level index 的期望 `sum(i*p_i)`，可为小数 | 不等于离散获胜 level，不能直接当未经定义的业务风险值 |
| `noul` | 固定语义 slot `[false,true]` 中第二项的概率 P(true) | 不是布尔值，也不是“本答案正确概率”；返回接近 0 可能是高置信 negative |
| `confidence`（choice/score） | `1-H(p)/log(k)`，k<2 特殊返回 1 | 分布集中度，未校准；不同 option 数的阈值不可直接移植 |
| `confidence`（noul） | `max(P(true),1-P(true))` | 与 choice/score 的同名字段语义不同 |
| `answer_confidence` | 通常是温度缩放分布的 `max(p)`；若安装 binning map 且无语言 override，则再映射 | 只有经本域校准并独立验证后才能作正确率解释；binning 后可能不等于返回概率最大值 |
| `action.act_probability` | 来自独立 action head 的 `act[r,0]` | 不等于主类概率，也不是 Alcor 授权/安全策略 |
| `abstention` | 显式设置 `min_confidence` 才写入 `passed` / `abstained` / `unevaluated` | 表示门的运行结果；不会删除原答案、取消动作或调用回退 |

以上定义来自 [`_decode_answers`](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1370-L1441)、[`answer_confidence` / entropy](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/common.py#L791-L839)、[gate 实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/confidence.py#L115-L341)。

`noul.labels` 只改变给模型看的文本，键必须恰为 false/true，返回语义仍为 P(true)。不能通过换 label 名称改变 true/false slot 的含义。[问题验证与接口契约](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/agent.py#L1100-L1144)

门优先读取 `answer_confidence`，缺失时当前实现回落到旧 `confidence`，两个均不可用则 `unevaluated`；没有 `min_confidence` 时字段完全缺席。比较是严格 `< threshold`，所以相等通过。支持按 `choice:2`、`choice:3-5`、`choice:6-10`、`choice:11+`（score/noul 同型）传阈值 map；未覆盖 bucket 回落 `default`，再回落 0，即不弃权。Alcor 若要求证据不足即回退，必须显式处理缺失、unevaluated、未拟合 bucket 和旧字段 fallback；不能将“无标志”当作已通过。[阈值解析、回退及 gate](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/confidence.py#L115-L341)

## 5. 可实际使用的训练格式、命令及校准

当前官方 `laya-train` 和 `laya train` 提供单设备训练入口；训练格式不是聊天 fine-tune 的 messages/assistant completion，也不是自行假设的 `{text,label}` JSONL。JSONL 每行一个 case，可包含多个问题；两种监督形式如下，各示例必须在真实文件中占一行：[训练说明](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/docs/finetune.md#L49-L70)、[CLI 参数实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/train_cli.py)

```jsonl
{"state":"重复扣费，请退款。","questions":{"department":{"type":"choice","instructions":"选择处理部门","criteria":{"billing":"支付、账单、退款","technical":"故障、软件问题"}},"refund_requested":{"type":"noul","instructions":"用户要求退款吗？"}},"expected":{"department":"billing","refund_requested":true}}
{"state":"重复扣费，请退款。","questions":{"department":{"type":"choice","instructions":"选择处理部门","criteria":{"billing":"支付、账单、退款","technical":"故障、软件问题"}}},"gold":{"department":{"probabilities":{"billing":0.95,"technical":0.05}}}}
```

`expected` 可给 choice label、noul boolean、score level（小数 level 可将质量分到相邻 level）；`gold` 则给各 question 的 teacher 分布，noul key 为 false/true、score key 为字符串 index。CSV 是另一入口，可显式配置 text/label column 生成 choice，不能把 CSV 契约偷换成 JSONL 契约。[训练数据契约](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/docs/finetune.md#L25-L70)

未来实验命令示例，**未执行**；`--base` 应使用预先固定并校验的本地 checkpoint 目录，以免命令把模型别名解析为随时间漂移的 Hub 默认分支：

```powershell
laya-train --data .\data\train.jsonl --base .\models\laya-multilingual-pinned --dry-run
laya-train --data .\data\train.jsonl --eval .\data\test.jsonl --base .\models\laya-multilingual-pinned --out .\artifacts\laya-domain --device cpu --freeze-encoder --epochs 4 --micro-batch 2 --grad-accum 8 --target-error 0.10
```

`--dry-run` 不加载模型权重或训练，但会使用 checkpoint tokenizer/config，因此不是“无需任何资产的静态 JSON 检查”。`--freeze-encoder` 确实关闭 encoder 参数梯度并将 encoder 置 eval，只训练其余 head，默认关闭。CPU 路径存在，但仍需要前向编码，不能宣称训练会很快或低内存。[dry-run 说明](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/docs/finetune.md#L72-L89)、[冻结实现](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/train.py#L649-L684)

训练默认 RLCD，也支持 soft-ce；train.py 先拆出 calibration slice，再训练，用 `fit_temperature_map` 拟合按 type/option bucket 的温度，拟合 `fit_abstention_thresholds` 并保存模型配置。小样本类型会保留 temperature=1 并警告；训练后评估若没有单独 `--eval`，可能只是 calibration slice 的拟合表现，报告明确区分 `in_sample_calibration` 与独立评估及 overlap。[训练/校准主流程](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/train.py#L990-L1228)

`fit_abstention_thresholds` 是 calibration 数据上的经验 cut，带小样本保守余量，源码明确说不提供形式 coverage 保证；拟合不足的 bucket 会省略。若 runtime 使用 binning map，阈值也必须在映射后尺度拟合。应冻结 train/calibration/test 分界，记录按任务、语言、option count 的 accuracy、ECE/Brier、risk-coverage、false allow/false deny、missing bucket；`--target-error 0.10` 不是上线后错误率承诺。[经验门拟合契约](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/calibrate.py#L442-L500)

## 6. CPU、Windows 与质量证据边界

源码有 CPU 设备选择和 CPU 训练路径；官方 README 给 Windows PowerShell venv/install 示例。因此可把 Windows CPU 列为“有上游支持入口，待本机实验”的候选，不应标记为已兼容或已验收。此次读取的主 CI Python matrix 在 ubuntu-latest 上跑 CPU torch，不能拿它证明 Windows 真实模型启动、推理或训练通过。[设备选择](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/laya/train.py#L528-L537)、[官方安装文档](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/README.md)、[主 CI](https://github.com/NandhaKishorM/laya/blob/118d361a774c9a28cd02a78d6cf4d2af0614f422/.github/workflows/ci.yml#L79-L120)

multilingual checkpoint 的温度为 `[1,1,1]` 且无 per-option buckets；默认应按未校准资产处理。官方模型卡还提示 noul/score、较多选项和低资源语言等弱点。模型卡的 T4 延迟、语言覆盖与 benchmark 是上游公开测量，不能外推本机 CPU 延迟、中文业务准确率或 Alcor 端到端收益。非生成式能避免自由文本格式解析问题，仍会做错分类、受候选/标签/上下文变化影响；不能把“无文本生成”解释为“不出错”。[固定配置](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/rl_agent_config.json)、[模型卡 Limits](https://huggingface.co/convaiinnovations/laya-multilingual/blob/1720e3e3357cfe1e281542e223f8273b0890ca34/README.md)

未来本机验收至少要记录：OS/CPU/RAM、Python/Torch/Transformers 锁定版本、模型 repo/subfolder/revision/hash、启动至 loaded 时间、冷/热推理 p50/p95/p99、线程/并发/超时、峰值内存、中文真实案例及截断案例、门标志与真正动作回退的契约。以上均为待办，不是本次研究已完成项。

## 7. 讨论中需要纠正的常见说法

| 待纠正说法 | 本次核查后的表述 |
| --- | --- |
| multilingual 硬上限 1024 | 默认 1024；当前官方支持显式 8192，总预算含问题头，长文质量仍须评估 |
| 官方多语言模型是 0.6B/1B 聊天模型 | 模型卡约 322M，mmBERT encoder + decision head，无自回归输出 |
| `confidence` 就是答案正确概率 | choice/score 是熵集中度；应区分 answer_confidence，且本域校准未通过前不作正确率承诺 |
| multilingual 默认已校准 | 固定 checkpoint 温度全 1、无 bucket，默认未校准 |
| noul=0.1 是低置信 | 是 P(true)=0.1，二元答案可偏向 false；其原始 confidence 可为 0.9 |
| abstention 已阻止动作 | 只是响应元数据；原答案保留，Alcor 执行层必须处理 |
| 原生服务只能靠独立 laya-serve 项目 | 本次固定的官方 laya 包已包含 serve extra、同名 CLI 及 /health 路由 |
| Jev-compatible 可直接沿用阈值且不丢字段 | confidence 语义不同；strict 投影会删除 Laya 扩展 |
| 训练 JSONL 是任意 text/label 或 messages | 官方当前契约是 state/questions + expected 或 gold；CSV 有独立列映射入口 |
| CPU 头部训练等于已经可在本机实时运行 | 源码支持不等于本机测量，冻结 encoder 仍有前向成本 |
| HTTP 200、health ok 等于输入完整且模型可用 | 还须检查 loaded/revision/device、截断信息与实际预测探针 |
| 多问一次前向所以增加问题几乎免费 | 通常是 Q 个完整 question-state 行批量一次 forward，encoder 计算和内存仍增加；分模型/分块时还会有多次 forward |

本表是前述固定一手来源的归纳；没有把第三方转载、同名 fork 或社区性能宣称作为候选可行性的证据。
