# Alcor 进度与续接

更新：2026-10-31（Asia/Shanghai）。

## 本轮范围与结果

根据分享讨论最终选择，形成独立外部决策引擎工程方案，首期聚焦Stella自然委派Codex。已完成协议草案、schema/示例、数据与评测规范、Runtime独立工作包、当前源码及上游研究核对、工作包依赖登记。

P00状态为`documented`，只表示设计资产已交付；P01及后续运行能力未实现。Alcor当前不是Git仓库，未创建提交或远程仓库。

## 验证证据

- 浏览器读取分享讨论全部三轮；以最后的外部决策模型选择为基线。
- WSL GitNexus 1.6.12绑定`/mnt/e/stella/stella_project`，索引HEAD与源码HEAD `cf630612c05f8ff9f7c8c61192b060c77b676856`一致；query/context加源码复核。Docker查询超时，仅使用备用路径，没有重启服务。
- [源码快照](evidence/source-snapshot.json)记录引用文件SHA256、分支与已有修改；未改动Stella。
- `python scripts/check_design_assets.py`：结果记录于[evidence/design-validation.txt](evidence/design-validation.txt)。这是设计资产检查，不是服务或模型测试。

未运行：Laya加载/推理/训练、真实Codex任务、宿主API/QQ/WebChat、只读沙盒、写入审批、llama.cpp故障复现与恢复。上线结论为 **NOT READY**。

## 下一轮唯一主任务

从P01建立轻量Python工程、contracts、RulesBackend、API和client，不先安装torch或下载权重。实现schema之外的跨字段与上下文绑定校验、deadline/busy/unknown行为。P02人工裁决可独立开展，先冻结标签与family划分。

进入P03前需要P02数据；进入真实只读灰度前需要P05/P06和只读profile映射。P08暂阻塞：当前Cometa Codex后端未提供人工审批通道，inspect/modify也需显式映射可信profile。不得靠模型建议或可写默认profile绕过。

## 恢复工作时先读

先读[README](README.md)、[主方案](docs/plans/2026-10-31-alcor-engineering-plan.md)、[协议](docs/contracts/decision-v0.1.md)、[feature_list](feature_list.json)。如涉及Stella集成，重新读取其AGENTS并检查工作区/索引新鲜度，编辑前执行对应图影响分析。旧测试、图和上游版本不得自动视为最新验收。
