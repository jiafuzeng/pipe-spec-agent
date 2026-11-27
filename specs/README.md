# Spec 索引

本目录是技术规程问答 Agent 的功能规格基线。`00-constitution.md` 和 `01-requirements.md` 是现有项目约束与九题验收基线；本轮新增的功能 Spec 在此基础上细化实施行为。实现应遵循章程，条款事实和计算规则以审核后的 CJJ 181—2012 原文数据为准。

## 文档

- [00 项目章程](00-constitution.md)
- [01 需求与验收](01-requirements.md)
- [02 技术设计](02-technical-design.md)：两个交付物（`pipe-spec-agent`、`pipe-assessment-mcp`）、三个进程，以及目标目录结构
- [001 知识来源、检索与引用](001-knowledge-and-citations.md)
- [002 Agent 规划、追问与会话状态](002-agent-dialogue.md)
- [003 计算、MCP 与曲线](003-calculation-mcp.md)
- [004 Web 演示与项目交付](004-web-demo-and-deliverables.md)
- [006 RAG 文档导入与向量索引 V1](006-rag-ingestion-v1.md)
- [007 Agent 测试用例与 agentEval（TDD）](007-agent-eval-tdd.md)：先冻结可执行用例，再设计执行器；与 `ragEval` 分工
- [008 计算规则双人审核（T03）](008-rule-dual-review.md)：worksheet → A/B 对照 PDF → `validate_rules` → published
- [03 计算规则规格](03-calculation.md)
- [04 接口与参数槽位规格](04-interfaces.md)
- [05 实施任务与交付门禁](05-tasks.md)
- [技术实现方案](../docs/技术实现方案与Spec清单.md)（**若与本目录冲突，以本目录为准**）

## 状态约定

- `Draft`：初稿，开发前需要结合规程条款清单核验。
- `Approved`：需求方确认，可作为实现和验收基线。
- `Implemented`：实现已完成并有可复现验收记录。

本轮新增 Spec 状态为 `Draft`，不是对已有章程/需求状态的重新标记。严禁将未核验的公式、分档、等级或强制性要求标记为已批准。

## 变更流程

1. 先修改 Spec，描述用户可观察的行为、边界和验收场景。
2. 引用规程条款时记录条款号、印刷页码、PDF 页序及审核状态。
3. 按 TDD 将验收场景转为测试，先确认新测试失败，再实现最小改动使其通过，之后重构并运行回归测试。
4. 实现和测试引用对应需求 ID（例如 `KN-01`、`CAL-03`）；规格冲突或原文缺项时，增加未决决策，不自行推定业务规则。
5. 合并前核对 Spec、实现、测试结果、测试答卷和演示行为一致。

## 需求追踪矩阵

| 任务说明 | Spec | 主要验收场景 |
|---|---|---|
| 唯一知识源、混合检索与重排、条款号、无依据拒答 | 00、01、001 | KN-01 至 KN-07 |
| 规划、参数追问、同会话记忆 | 00、01、002 | AG-01 至 AG-06（场景 ID 见各节 `traces_to`） |
| 缺陷分值、RI/MI、绘图与 MCP | 00、01、003、04、008 | CAL-01 至 CAL-08；T03 双审见 008 / REV-01–05 |
| 计算规则双审与发布门禁 | 008、03 §7.0、05 T03 | worksheet / reviews / published；`validate_rules` |
| Web、九题演示、知识库导入、答卷和自查说明 | 01、004 | WEB-01 至 WEB-09 |
| LlamaIndex 文档切片、embedding 选择、Chroma 持久化与来源 metadata | 01、001、004、006 | ING-01 至 ING-09；`source_doc_id`=SHA-256 |
| Agent TDD 与评测执行器 | 007、02 §12、05 T14 | `agent_cases.json` 先红灯再实现 |
