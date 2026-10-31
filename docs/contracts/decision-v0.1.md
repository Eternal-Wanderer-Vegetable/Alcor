# Alcor 决策协议 v0.1

状态：设计草案；尚未实现 HTTP 服务。JSON Schema 是字段级约束，本文件规定跨字段与宿主语义。协议版本、问题模板版本、模型版本和校准版本分别演进。

## API

`POST /v1/decisions` 接收 `DecisionRequest`，返回 `DecisionResponse`。这是 Alcor 自有接口，不是 Laya `/v1/systemone` 的透传或同名替换。

- 合法请求发生推理超时、busy、版本异常等业务故障时返回结构化 `abstain`，不伪装 `chat` 的肯定分类。
- HTTP 400/422：输入/schema/上下文 digest 错误；401/403：client认证失败；413：请求体超过配置上限；503：API本身未就绪。宿主对这些状态一律不新增自然委派。
- 首个请求体上限拟定64KiB；文本长度与实际token数另计；不可用字符上限充当模型token预算。
- 超时设置使用客户端传入的相对 `deadline_ms`，服务端取自身上限与该值的较小值，并在入口转成 monotonic deadline；排队消耗同一个预算。
- API重放纯判断无副作用，但宿主不得把同一决策响应重复转成不同任务。

## 请求结构

完整例见 [request](../../examples/decision-request.json) 与 [request schema](../../schemas/decision-request.schema.json)。

| 字段 | 谁提供 | 语义 |
| --- | --- | --- |
| `schema_version` | client | 固定`0.1`，不兼容版本显式拒绝 |
| `request_id` | 可信宿主 | 每次决策调用的标识，不等于任务幂等键 |
| `context_digest` | 可信宿主+服务重算 | 下述`context`按约定规范化的SHA-256 |
| `deadline_ms` | client | 相对端到端预算，1–2000ms |
| `context.current_message` | 可信入口 | 当前真正用户消息、说话人、来源类型 |
| `context.history` | 会话存储 | 有界完整消息单元；每项保留speaker及role |
| `context.proposal` | 宿主方案存储 | 0或1个有效待执行方案引用；空不能猜 |
| `context.integrity` | normalizer | complete/budget_exceeded/missing_reference/unknown |
| `context.host_facts` | 已认证宿主 | 触发类型、工作区是否已绑定、候选能力健康及确定性短工具摘要 |

v0.1 digest规范：Python参考为`json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`；context schema不含浮点数且拒绝重复键，跨语言实现必须通过固定fixture验证字节一致性。不在此版本声称支持任意JSON规范化。新增浮点字段前应改为明确的跨语言规范并升级协议。

principal、source ID及profile绑定来自入口认证，不能从模型生成的JSON直接灌入`host_facts`。远端部署需要认证client、授权宿主范围与传输加密；本地默认只监听loopback。Alcor不签发用户grant，也不输出任意cwd/profile/命令路径。

消息的`source_kind=direct|quoted|notification|agent_result`用于描述内容来源；直接消息里仍可能包含引述，不能只凭该字段肯定执行意图。history里的assistant建议不是用户授权。历史用户的授权必须由宿主另行验证，不能仅靠分类器推断的说话人。

`proposal`记录id、owner、revision、内容digest、目标scope和相关消息IDs。宿主解析相同会话及用户的方案引用后才可填入；Alcor可判断“执行既定方案”的语义，但受理前仍由宿主确认引用有效、未过期且目标范围一致。未知、多候选或跨用户方案要求澄清。

`host_facts.coding_agent_state`是提示决策可行性的快照，不能代替受理时重新probe或权限检查。`workspace_bound=true`只表示有绑定，不表示有写权限。

## 响应与概率

完整例见 [response](../../examples/decision-response.json) 与 [response schema](../../schemas/decision-response.schema.json)。

- `assessment`是多维语义；`recommendation`是Alcor建议。宿主可拒绝、降级、澄清，但不可自行把`abstain`扩大成委派。
- `status=unknown`必须是`abstain/none/none`；`status=decided`才表示产生语义建议，不表示通过执行准入。
- `delegation_probability`只表示当前标注定义下“用户请求现在执行且需要编码代理”的领域校准概率，不是Laya entropy confidence，也不是权限概率。无对应校准模型时为null。
- `calibration_id`与概率必须同空/同存在；评测/校准bundle不匹配时不得用于自动委派。不能将几个独立问题的概率相乘并称作已校准联合概率。
- `reason_codes`为可观测枚举，禁止自由推理链或包含凭据。用户可见澄清由宿主根据代码和缺失字段渲染。
- `evidence_message_ids`只能引用本请求当前/history消息和proposal引用的消息。服务必须验证存在性；证据引用是模型证据，不是执行grant。
- `versions`标识backend、模型、template、normalizer、policy、bundle。替换任一组成部分后重校准；不把大模型教师ID当运行模型版本。

## 语义组合表

| assessment / 事实 | recommendation | reason code |
| --- | --- | --- |
| chat / discuss / explain，未要求实际执行 | chat, none, none | discussion_only / knowledge_or_example |
| execute + repository_inspection + inspect + complete + self_request | delegate, coding_agent, inspect | execution_requested |
| execute + repository_change + modify + complete + self_request | delegate, coding_agent, modify | execution_requested |
| execute但缺少当前目标/方案引用 | clarify, none, none | missing_context / ambiguous_reference |
| quotation/hypothetical且未包含当前用户独立执行要求 | chat, none, none | quoted_or_hypothetical |
| 确定性短工具足以处理且请求无独立长任务 | chat, none, none | local_tool_available |
| 编码代理不可用但用户明确需要代理 | abstain, none, none | backend_unavailable |
| 研究类请求且首版不支持该范围 | abstain, none, none | unsupported_scope |
| 超预算、必要字段缺失、矛盾分类、低于门限、上游截断 | abstain, none, none | 对应错误码 |

这里的chat表示Alcor不接管自然委派，交回宿主原处理路径，不强制屏蔽普通工具。`research`维度保留是为识别范围外任务，首版不通过模型自动执行无限制联网研究。

跨字段必须满足：delegate的target只能coding_agent，mode只能inspect/modify；非delegate的target/mode都必须none；未知或不完整上下文不能delegate；inspect只能对应repository_inspection、modify只能对应repository_change；上下文证据/引用校验失败必须unknown。

## 宿主准入结果单独保存

HostAdmission不属于Alcor模型响应。宿主建议保存`decision_request_id`、`source_request_id`、`context_digest`、`outcome=allowed|clarify|denied|unavailable`、`reason_code`、可信principal、workspace/profile绑定、grant引用（若有）、最终sandbox、policy revision和可选task_id。

模型响应中不提供`requires_approval=false`或`authorized=true`之类可误用字段。已存在的授权由宿主读取，并核验目标、时效和范围；缺少授权的写入建议不能提交到一个恰好可写的默认profile。

Cometa幂等以可信source request为根，不以模型生成objective或request_id为根；重试沿用原key。实际提交前重新核验profile/backend/workspace与方案版本，防止决策后配置变化。

## 必要契约用例

普通问答、写代码示例、讨论重构、直接查仓库、明确改仓库、多轮“照此做”、跨用户引述、缺引用、撤销旧授权、同source重复请求、超时、队列满、上游HTTP200但truncated、strict模式删字段、bundle变化、只读映射到可写默认profile、Codex不支持人工审批。

实现阶段必须测试这些跨字段与宿主行为；本轮JSON Schema检查只验证结构及少量枚举关联，不等同这些行为已实现。
