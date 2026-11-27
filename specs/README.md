# Spec 索引

本目录按**项目开发流程**组织，是 Pipe Spec Agent / 管道规程工作台的规格基线。  
条款事实与计算规则以审核后的《CJJ 181—2012》原文为准；实现、提示词、测试与答辩均须遵守治理章程。

若与 `docs/` 冲突，以本目录为准。

## 流程总览

```text
治理 → 需求 → 设计 → 开发 → 测试 → 交付
```

| 阶段 | 目录 | 做什么 |
|---|---|---|
| 1. 治理 | [`01-governance/`](01-governance/) | 不可妥协边界：知识源、计算、会话表达 |
| 2. 需求 | [`02-requirements/`](02-requirements/) | 产品范围、能力、九题验收 |
| 3. 设计 | [`03-design/`](03-design/) | 架构、接口契约、计算规则规格 |
| 4. 开发 | [`04-development/`](04-development/) | 可实施的功能 Spec（RAG / Agent / MCP / Web / 双审） |
| 5. 测试 | [`05-testing/`](05-testing/) | Agent TDD 与 `agentEval` 机器契约 |
| 6. 交付 | [`06-delivery/`](06-delivery/) | 任务依赖、门禁与发布完成条件 |

推荐阅读与变更顺序：先改上游（治理/需求/设计），再改开发 Spec，再补测试用例，最后更新交付任务状态。

## 文档清单

### 1. 治理

- [项目章程](01-governance/constitution.md)

### 2. 需求

- [产品需求与九题验收](02-requirements/product-requirements.md)

### 3. 设计

- [技术设计](03-design/technical-design.md)：双交付物、三进程、目录与职责
- [接口与参数槽位](03-design/interfaces.md)：HTTP / MCP / SSE 唯一契约
- [计算规则规格](03-design/calculation-rules.md)：公式、算例、夹具策略

### 4. 开发（功能 Spec）

- [知识来源、检索与引用](04-development/knowledge-and-citations.md)
- [Agent 规划、追问与会话](04-development/agent-dialogue.md)
- [计算、MCP 与曲线](04-development/calculation-mcp.md)
- [RAG 文档导入与向量索引 V1](04-development/rag-ingestion-v1.md)
- [计算规则双人审核（T03）](04-development/rule-dual-review.md)
- [Web 演示与项目交付](04-development/web-demo-and-deliverables.md)

### 5. 测试

- [Agent 测试用例与 agentEval（TDD）](05-testing/agent-eval-tdd.md)

### 6. 交付

- [实施任务与交付门禁](06-delivery/tasks-and-gates.md)

### 外部参考

- [技术实现方案](../docs/技术实现方案与Spec清单.md)（背景材料；冲突时以本目录为准）

## 状态约定

- `Draft`：初稿，开发前需结合规程原文核验。
- `Approved`：可作为实现与验收基线。
- `Implemented`：实现完成且有可复现验收记录。

未核验的公式、分档、等级或强制性要求 **不得** 标为 `Approved`。

## 变更流程

1. 按阶段修改 Spec：先写清可观察行为、边界与验收场景。
2. 引用规程时记录条款号、印刷页码、PDF 页序及审核状态。
3. TDD：验收场景 → 失败测试 → 最小实现 → 重构与回归。
4. 实现与测试引用需求/场景 ID（如 `KN-01`、`CAL-03`）；缺原文依据标「未决」，不自行推定。
5. 合并前核对 Spec、实现、测试、答卷与演示一致。

## 需求追踪矩阵

| 任务说明 | Spec | 主要验收场景 |
|---|---|---|
| 唯一知识源、混合检索与重排、条款号、无依据拒答 | 治理、需求、开发/knowledge | KN-01 至 KN-07 |
| 规划、参数追问、同会话记忆 | 治理、需求、开发/agent-dialogue | AG-01 至 AG-06 |
| 缺陷分值、RI/MI、绘图与 MCP | 需求、设计/interfaces、开发/calculation-mcp、rule-dual-review | CAL-01 至 CAL-08；REV-01–05 |
| 计算规则双审与发布门禁 | 开发/rule-dual-review、设计/calculation-rules、交付 T03 | worksheet / reviews / published |
| Web、九题演示、答卷与自查 | 需求、开发/web-demo | WEB-01 至 WEB-09 |
| 导入、切片、embedding、Chroma | 需求、开发/rag-ingestion、knowledge | ING-01 至 ING-09 |
| Agent TDD 与评测执行器 | 测试/agent-eval-tdd、设计/technical-design、交付 T14 | `agent_cases.json` |

## 旧路径对照

| 旧路径 | 新路径 |
|---|---|
| `specs/00-constitution.md` | `specs/01-governance/constitution.md` |
| `specs/01-requirements.md` | `specs/02-requirements/product-requirements.md` |
| `specs/02-technical-design.md` | `specs/03-design/technical-design.md` |
| `specs/03-calculation.md` | `specs/03-design/calculation-rules.md` |
| `specs/04-interfaces.md` | `specs/03-design/interfaces.md` |
| `specs/05-tasks.md` | `specs/06-delivery/tasks-and-gates.md` |
| `specs/001-knowledge-and-citations.md` | `specs/04-development/knowledge-and-citations.md` |
| `specs/002-agent-dialogue.md` | `specs/04-development/agent-dialogue.md` |
| `specs/003-calculation-mcp.md` | `specs/04-development/calculation-mcp.md` |
| `specs/004-web-demo-and-deliverables.md` | `specs/04-development/web-demo-and-deliverables.md` |
| `specs/006-rag-ingestion-v1.md` | `specs/04-development/rag-ingestion-v1.md` |
| `specs/007-agent-eval-tdd.md` | `specs/05-testing/agent-eval-tdd.md` |
| `specs/008-rule-dual-review.md` | `specs/04-development/rule-dual-review.md` |
