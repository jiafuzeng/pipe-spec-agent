# 007 Agent 测试用例与 agentEval（TDD）

状态：Draft  
范围：先冻结可机器检查的 Agent 测试用例，再设计 `agentEval` 执行器。Web 与评测共用同一 Agent 入口。实现顺序是：写失败测试 → 最小实现 → 重构 → 回归。

## 1. TDD 顺序

1. **定用例契约**：每条用例声明前置条件、输入回合、期望动作、工具约束、引用、事件和可核对数值。
2. **写红灯测试**：`agentEval` 或 `tests/` 先按契约断言；当前 `rag/dialogue.py` 应对红灯。
3. **最小实现**：只改让该用例变绿所需的编排、检索或 MCP 契约。
4. **重构**：目录迁到 `app/agent/`、抽离 MCP 时，同一批用例保持绿。
5. **禁止**：评测走另一套简化对话；禁止用假日志、假曲线或未审核规则冒充通过。

与 `ragEval` 的分工：

| 层 | 输入 | 判什么 | 不判什么 |
|---|---|---|---|
| `ragEval` | 只发 `query` | 证据正文、条款、PDF 页是否进 Top-K | 回答措辞、追问、计算 |
| `agentEval` | 会话回合（可多轮） | 动作、引用、工具次数、槽位、事件、算例数值、拒答 | 文笔优劣、未写入契约的措辞 |

`agentEval` 引用条款时，应能追溯到已发布索引；证据真伪仍以 `ragEval` / `rag_validation.json` 为准。

## 2. 先设计测试用例

### 2.1 用例字段

```json
{
  "id": "AG-T07-01",
  "origin": "任务书第7题 / AG-01-A",
  "tags": ["composite", "clarify", "plot", "multi_turn"],
  "precondition": {
    "rules": "approved",
    "index": "active_approved",
    "session": "new",
    "subject_id": "pipe-A",
    "confirmed_parameters": []
  },
  "turns": [
    {
      "message": "说明 RI 公式及 K 分档；固定其余参数，令 K=0,3,6,10 画 RI-K 曲线。",
      "expect": {
        "action": "clarify_then_explain",
        "citations_any_of": ["8.3.4", "表8.3.4-1"],
        "tool_calls": {"calculate_index": 0, "plot_curve": 0},
        "missing_parameters": ["F", "E", "T"],
        "events_include": ["plan_step", "clarification_required"],
        "same_run_continues": true
      }
    },
    {
      "message": "F=6，E=6，T=0，按刚才四个 K 继续。",
      "expect": {
        "action": "calculate_and_plot",
        "tool_calls": {"calculate_index": 4, "plot_curve": 1},
        "reuse_parameters": ["F", "E", "T"],
        "results": [
          {"K": 0, "RI": 4.5},
          {"K": 3, "RI": 4.8},
          {"K": 6, "RI": 5.1},
          {"K": 10, "RI": 5.5}
        ],
        "chart": {"required": true, "points": 4},
        "events_include": ["tool_call", "chart", "answer"]
      }
    }
  ]
}
```

字段约定：

| 字段 | 含义 |
|---|---|
| `precondition.rules` | `approved` / `pending_review`；`fixture_rules=true` 时经 `RULE_FIXTURE=1` 加载夹具包 |
| `precondition.index` | `active_approved` / `pending_only` / `empty` |
| `precondition.mcp` | 可选 `offline` |
| `turns[]` | 同一 `session_id` 上的有序消息；默认同一 `run_id` 可跨轮恢复 |
| `expect.action` | 机器枚举，见 §2.2；**唯一判分枚举** |
| `expect.tool_calls` | 工具名 → 恰好次数；未列出的计算类工具默认必须为 0 |
| `expect.citations_*` | 回答或证据事件中必须出现的条款/表号 |
| `expect.missing_parameters` | 追问清单必须覆盖的字段名（简单题） |
| `expect.missing_parameter_groups` | 题 8 等：每组 `any_of` 至少命中一个（见 `04` §2） |
| `expect.results` / `chart` | 仅 `fixture` 或已发布规则且参数齐备时生效；报告标 `rule_mode` |
| `expect.refusal_text` | 拒答必须包含章程固定句 |
| `expect.partial` | 子问题分别标记 `answered` / `refused` / `pending` |

### 2.2 动作枚举

| `action` | 通过条件 |
|---|---|
| `answer` | 有 `answer`；计算工具次数为 0（纯计算单次无图时可有 `calculate_index`）；引用满足契约 |
| `compare` | 有对比结构或分点；引用覆盖契约条款 |
| `clarify` | 有 `clarification_required`；`calculate_index`/`plot_curve` 为 0 |
| `clarify_then_plan` | 首轮追问或带假设确认；不得在缺关键条件时给出违规推荐 |
| `clarify_then_explain` | 可解释公式/分档并追问；`calculate_index`/`plot_curve` 为 0；应有进程内检索或证据事件（`search_clauses` 次数 ≥1 或 `evidence` 事件） |
| `calculate_and_plot` | 计算次数与自变量点数一致；有图表资源或等价 chart 事件 |
| `partial_answer` | 有依据子问作答，无依据子问拒答；不得臆测补全 |
| `refuse` | 全文使用固定拒答句；无虚构条款 |
| `block_unreviewed` | 待审规则下无数值结果；返回 `RULE_NOT_PUBLISHED` 或等价说明 |

#### 与 `agent_validation.json` 的映射（双文件长期并存）

| `agent_validation.expected_action`（叙述） | 规范 `expect.action` / 多轮拆分 |
|---|---|
| `clarify_then_plot`（SPEC-07 / SPEC-09） | **废弃作单轮标签**。题 7：首轮 `clarify_then_explain`，次轮 `calculate_and_plot`（见 `AG-T07`）。题 9：首轮 `clarify`（流砂），后续轮 `calculate_and_plot`（`AG-T09` 领域发布后） |
| 其余（`answer`/`compare`/`clarify`/…） | 与上表同名，一一对应 |

`run.py` **只读** `agent_cases.json` 判分；`agent_validation.json` 保留题面与人工 acceptance，不参与机器枚举。

### 2.3 用例分层（先写这些，再实现）

**L0 契约冒烟（无大模型也可跑替身）**

| ID | 覆盖 | 红灯含义 |
|---|---|---|
| `AG-L0-01` | 新建会话返回 `session_id`；首事件含 `turn_id`/`run_id`/`event_id` | 五个标识未落地 |
| `AG-L0-02` | MCP `offline` 时条文问答仍可 `answer`；计算步骤明确失败 | 检索仍经 MCP |
| `AG-L0-03` | 幂等键重复调用 `calculate_index` 只生成一个结果 | 每次 `uuid4` |
| `AG-L0-04` | `pending_review` 规则触发 `block_unreviewed` | 未审规则可算 |

**L1 单轮确定性（九题拆条 + AG/KN/CAL）**

| ID | 来源 | 核心断言 |
|---|---|---|
| `AG-T01` | 第1题 | 引用 1.0.1、1.0.2；无计算工具 |
| `AG-T05` | 第5题 | 至少 3 个检索 `step_id`；声纳边界、井先于管、表9.0.2-1 可分别定位；允许部分完成 |
| `AG-T08` | 第8题 | `clarify`；`missing_parameter_groups` 覆盖 F\|缺陷、K、E\|D、T\|土质；计算次数 0 |
| `AG-V11` | 规程外收费 | `refuse` + 固定句 |
| `AG-V12` | 虚构条款 | `refuse`；不得采信 99.8.7 |
| `AG-V14` | 待审公式 | `block_unreviewed` |

**L2 多轮状态**

| ID | 来源 | 核心断言 |
|---|---|---|
| `AG-T07` | 第7题 + V09 | 首轮追问+可检索说明；次轮同 `run_id`；4 次计算 + 1 次绘图；RI 与 `03` §7.1 一致 |
| `AG-T09` | 第9题 | 流砂不落 T；确认前无 RI；T 给定后曲线点与 `03` §7.2 一致；领域未发布前 `blocked_until=T03_domain` |
| `AG-V10` | AG-04-B | 换管段不静默复用；必须澄清或显式授权 |
| `AG-V13` | AG-06-A | 有依据子问作答，规程外子问拒答 |
| `AG-PARAM-01` | 设计 §3.1 | 「管径改成 1200」后旧 E/结果失效，其他确认值保留 |
| `AG-T-MI-01` | CAL-08 | MI 未发布时 `block_unreviewed`；范围保留但不强行实现 |

**L3 方案与比较**

| ID | 来源 | 核心断言 |
|---|---|---|
| `AG-T02` / `AG-T04` | 第2/4题 | 分方法引用；不自造效率排名 |
| `AG-T06` | 第6题 | 先追问关键缺项；已知条件下标出不得/不满足项 |

**双文件并存（已冻结）**：`agent_validation.json` = 题面 + 人工 acceptance；`agent_cases.json` = 唯一机器契约。多轮题在 `agent_cases` 中共用 `session`/`run`；`agent_validation` 的「每题独立会话」仅适用于无跨轮 precondition 的单轮叙述题。ID 映射：`SPEC-07`↔`AG-T07`，`SPEC-08`↔`AG-T08`，`V10`↔`AG-V10`，`V13`↔`AG-V13`。

**CI 范围（已冻结）**：默认只跑 `ci=true` 子集；完整九题与 L2/L3 本地或演示前跑。

### 2.4 判分规则

对每个 `turn.expect`：

1. **动作**：实际动作 ∈ 允许集合（由事件推断：仅有追问 → `clarify`；有 chart → `calculate_and_plot` 等）。
2. **工具**：名称与次数精确匹配；缺参轮次计算类必须为 0。
3. **引用**：`expected_citations` 全部出现在证据或回答引用列表；拒答类必须为空引用。
4. **参数**：`missing_parameters` 被追问清单覆盖；若有 `missing_parameter_groups`，则每组 `any_of` 至少命中一个；`reuse_parameters` 不得再次追问。
5. **数值**：`results` 与工具返回一致（`decimal` 字符串或约定精度）；与回答中的数一致，回答多出来的数判失败；报告写 `rule_mode`。
6. **图表**：需要时存在 `resource_id` 或可取回的 chart 事件；点数与自变量一致。
7. **部分完成**：`partial` 子项各自满足 answered/refused。
8. **跨轮**：标记 `same_run_continues` 时，后轮 `run_id` 与前轮相同。

汇总指标（报告用）：

- `action_pass_rate`
- `citation_pass_rate`
- `tool_constraint_pass_rate`
- `numeric_pass_rate`（仅含 results 的用例）
- `multi_turn_resume_pass_rate`
- `refusal_pass_rate`

任一项契约字段失败 → 该用例失败；不因文笔扣分。

## 3. 再设计 agentEval

### 3.1 目录

```
agentEval/
├── README.md                 # 怎么跑、替身、门禁
├── agent_validation.json     # 题面与人工验收叙述（已有）
├── agent_cases.json          # TDD 可执行用例（按 §2 字段）
├── fixtures/                 # 规则包、MCP 替身响应、会话种子
├── run.py                    # 执行器：建会话 → 逐轮调用 Agent → 判分
└── report.schema.json        # 报告 JSON 形状（可选）
```

主项目测试中的薄封装：

```
tests/test_agent_l0.py        # L0 冒烟，CI 必跑
tests/test_agent_cases.py     # 读取 agent_cases.json 中标记 ci=true 的子集
```

完整九题与 L2/L3 可在本地或演示前跑，允许依赖已发布规则与可控模型/替身。

### 3.2 执行器行为

`agentEval/run.py`：

1. 加载 `agent_cases.json`。
2. 按 `precondition` 准备：规则状态、索引、MCP 在线/离线、会话种子参数。
3. 调用 **与 Web 相同** 的入口（目标：`app.agent.workflow`；过渡期可适配现有 dialogue，但不得复制业务分支）。
4. 收集结构化轨迹：事件列表、工具调用、确认参数、引用、结果 ID、图表资源 ID。
5. 按 §2.4 判分，写出报告：

```json
{
  "mode": "stub_mcp|live_mcp",
  "agent_entry": "app.agent.workflow",
  "summary": {
    "total": 0,
    "passed": 0,
    "action_pass_rate": 0,
    "citation_pass_rate": 0,
    "tool_constraint_pass_rate": 0
  },
  "results": [
    {
      "id": "AG-T07",
      "passed": false,
      "turns": [{"index": 0, "passed": false, "failures": ["calculate_index expected 0 got 1"]}]
    }
  ]
}
```

6. `GET /api/v1/evaluations/agent` 只读最近一次报告，不在请求里现场重跑长套件（避免拖垮 API）。

### 3.3 替身与环境

| 依赖 | CI 默认 | 完整验收 |
|---|---|---|
| 聊天模型 | 固定 stub / 录制响应；默认 `EVIDENCE_LLM_VERIFY=0`（条款匹配+重排） | 可开 LLM 复核，但契约仍机器检查 |
| MCP | `fixtures/` 替身，支持 offline、timeout、idempotent hit | 可打到 `pipe-assessment-mcp` |
| 规则包 | 测试用 `approved` 最小 RI 包 + `pending` 包 | 与演示发布包版本号写入报告 |
| 索引 | 已审核 CJJ 活动索引或测试夹具 collection | 与 `ragEval` 相同来源哈希 |

### 3.4 与实现任务的挂接

| 开发项 | 先红的用例 | 变绿标准 |
|---|---|---|
| 五个标识与 SSE | `AG-L0-01` | 首事件字段齐全 |
| MCP 离线检索 | `AG-L0-02`、条文 L1 | 检索不经 MCP |
| 幂等重试 | `AG-L0-03` | 同键单结果 |
| 追问闸门 | `AG-T08`、`AG-T07` 首轮 | 计算次数为 0 |
| 跨轮 run | `AG-T07` 次轮、`AG-V09` | 同 `run_id`，四点数值正确 |
| 管段隔离 / 改参 | `AG-V10`、`AG-PARAM-01` | 不静默复用；依赖失效 |
| 部分完成 | `AG-T05`、`AG-V13` | 子问分别作答/拒答 |
| 待审阻断 | `AG-V14`、`AG-L0-04` | 无 RI 数值 |
| 第9题推导 | `AG-T09` | 与算例一致且流砂先澄清 |

## 4. 验收

**Given** `agent_cases.json` 已按 §2 写入 L0 与至少第 7/8 题用例，且执行器已实现。  
**When** 在未改 Agent 前运行 `agentEval/run.py`。  
**Then** 对应当前单体对话的用例为失败（红灯），报告指出动作/工具/标识类失败原因。

**Given** 对应功能按 TDD 实现。  
**When** 再跑同一命令。  
**Then** 目标用例变绿；`ragEval` 不回归；Web 九题入口仍走同一 Agent 入口。

## 5. 未决项

- 真实模型评分是否另加人工抽检清单（本 Spec 机器契约之外；机器契约不依赖此项）。
- L1/L2/L3 其余用例正文补全时机（不阻塞 L0 + T07/T08 开工）。
