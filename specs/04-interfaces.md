# 04 接口与参数槽位规格

状态：Draft  
本文是 Agent / HTTP / MCP 的**唯一契约枢纽**。字段与工具以人工核验的 CJJ 181—2012 为准；未发布规则不得产出指数或等级。与 `02-technical-design.md` §9–§12、`007-agent-eval-tdd.md` 冲突时，以本文 + `02` §12 修订条款为准，并回写本文。

## 1. 聊天与执行 API

### `POST /api/v1/sessions`

创建会话，返回 `session_id`、`created_at`、会话状态。

### `GET /api/v1/sessions/{session_id}`

刷新后恢复消息摘要、当前 `subject_id`、已确认参数、待回答问题和进行中的 `run_id`。

### `POST /api/v1/sessions/{session_id}/turns`

请求包含 `message` 和可选 `subject_id`（缺省 `"default"`）。响应以 SSE 输出。

**SSE 约定（编码前冻结）：**

1. `Content-Type: text/event-stream`；每条 `data:` 为 JSON 对象。
2. **首事件**（`event_id=0`）字段至少：`turn_id`、`run_id`、`event_id`、`type`（建议 `plan_step` 或 `run_started`）。
3. 后续事件 `event_id` 严格递增；适用步骤带 `step_id`。
4. `error.code` 使用本文 §4 **大写蛇形**错误码（如 `TOOL_UNAVAILABLE`）。实现层若暂有小写别名，须在响应中同时给出规范码，Phase 2 后只保留大写。
5. 断开连接不取消未声明停止的 run；用 `GET .../events?after_event_id=` 续读。

事件种类：

- `plan_step`：步骤类型、状态、可读标签、`step_id`
- `clarification_required`：槽位清单及原因（见 §2 `missing_parameter_groups`）
- `evidence`：条款引用卡片（证据 ID、条款/表号、页序、摘录）
- `tool_call`：工具名、调用 ID、状态、输入/输出摘要、耗时、`step_id`
- `answer`：最终文本、引用 ID、结果/图表资源 ID
- `chart`：仅含 `resource_id`（不塞整图 Base64）
- `error`：稳定错误码、可否重试、恢复提示

API 不输出模型隐藏思维链。输入原文与参数确认事件分开存储。

### `GET /api/v1/runs/{run_id}`

查询步骤、状态、工具结果引用及失败原因。

### `GET /api/v1/runs/{run_id}/events?after_event_id=`

断线后续读。断开只停接收，不取消未声明停止的 run。

### `GET /api/v1/artifacts/{resource_id}`

经主项目代读 MCP 图表等资源。浏览器不接触 MCP 凭证或容器路径。

**图表存储（编码前冻结）：** MCP 将文件落在自身数据目录（默认 `data/mcp/artifacts/{resource_id}.png`，可用环境变量覆盖根路径）；主项目只存 `resource_id` 并代读。运维备份策略可后定，逻辑 ID 不变。

### `/api/v1/knowledge/...`

沿用文档导入、预览、审核和删除（见 `006-rag-ingestion-v1.md`）。

### `/api/v1/evaluations/...`

| 接口 | 用途 |
|---|---|
| `GET /api/v1/evaluations/rag` | 最近一次 `ragEval` 报告；兼容旧路径 `GET /api/v1/knowledge/rag-eval` |
| `GET /api/v1/evaluations/agent` | 最近一次 `agentEval` 报告；不在请求内现场重跑长套件 |

### `GET /health`

顶层在应用可服务时可为 `ok`。分量至少含 `app`、`registry`、`embedding`、`chat_model`、`reranker`、`mcp`。MCP 不可达时 `mcp.status=unavailable`，不拖垮导入与条文检索。Compose 中 backend **不**硬依赖 mcp 容器。

## 2. RI/MI 槽位清单

RI 由 F、K、E、T 等参与式 8.3.4，并需要 S、Smax 等中间量。完整字段以已发布 / 夹具 Schema 为准；下列为题 7–9 的工作清单。`source_status=pending` 的字段不得当作已发布必填项硬编码进产品。

| 类别 | 槽位 | 用户提供/工具推导 | 当前要求 |
|---|---|---|---|
| 管段识别 | `subject_id` | 会话生成或用户指定 | 隔离同会话参数 |
| 管径 | D（mm） | 用户或已确认值 | 映射表 8.3.4-2 → E；边界待复核后冻结 |
| 地区重要性 | K 或道路描述 | 用户明确给 K；文字映射需确认 | 表 8.3.4-1 |
| 土质 | 表列类别或 T | 用户选列或直接给 T | 表 8.3.4-3；「流砂」不得擅自映射 |
| 缺陷记录 | 类型、等级等 | 用户提供；工具查表 | 表 8.2.3 |
| 缺陷空间关系 | 纵向间距 | 用户提供 | 8.1.3 / 8.1.4 分组与合并 |
| S / Smax / F | 中间量 | MCP 推导；用户亦可直接确认 F（夹具/演示捷径） | **不得**把 F 列为「唯一必填且不可由缺陷替代」 |
| 管龄 / 管材 | 年、材质 | 用户提供 | 仅周期说明；不进式 8.3.4 |
| MI 专属 | 由 MI Schema 定义 | 用户或工具 | 与 RI 分版维护；未审前阻断 |

### 字段冻结准则

- 每项含 `name`、`label_zh`、`type`、`unit`、`required_when`、`enum/range`、`description`、`evidence_refs`、`source_status`。
- 文字只能在唯一映射时转成枚举；否则返回候选项。
- 用户显式给出的 T 视为确认；曲线每点分别记录 T。
- 同管段可复用已确认值；切换管段不得静默复用。
- 题 8 必填清单只从 Schema 生成，并用分组「或」关系表达（见下）。

### `missing_parameter_groups`（题 8 / 追问）

`clarification_required` 载荷推荐：

```json
{
  "groups": [
    { "id": "F_or_defects", "any_of": ["F", "defects"], "label_zh": "缺陷参数 F，或缺陷记录供查分推导" },
    { "id": "K", "any_of": ["K"], "label_zh": "地区重要性参数 K" },
    { "id": "E_or_D", "any_of": ["E", "D"], "label_zh": "管道重要性 E，或管径 D" },
    { "id": "T_or_soil", "any_of": ["T", "soil"], "label_zh": "土质参数 T，或表 8.3.4-3 列名" }
  ]
}
```

`agentEval` 判定：每个 group 至少有一个 `any_of` 字段出现在追问清单或等价说明中即通过该组；全部 group 满足才算追问完整。夹具 RI 包若暂无缺陷查分，允许 group `F_or_defects` 在追问中只露出 `F`，但仍不得禁止产品路径收集缺陷。

## 3. 检索与 MCP 工具归属

### 3.1 主项目（进程内）

#### `search_clauses`

不在 MCP 注册。Agent / `app/rag` 进程内调用。

入参：`query`、可选 `filters`、`top_k`。  
出参：证据 ID、原文、条款或表号、PDF 页序、来源版本；仅 `approved` 索引。

### 3.2 MCP（`pipe-assessment-mcp`）

只提供计算与绘图。不得依赖主项目 Chroma / 会话库。

#### `get_calculation_schema`

入参：`calculation_type`（`RI` \| `MI` \| `defect_score`）、可选 `rule_version`（缺省为当前已发布版；`RULE_FIXTURE=1` 时可为夹具版）。  
出参：`status`（`approved` \| `pending_review`）、`rule_version`、字段 Schema、作用说明、出处。未发布时 `fields` 可空并给原因。

一次 `run` 在首次成功取得 Schema 后锁定 `rule_version`；后续查分、计算、绘图必须传同一版本。

#### `lookup_defect_score`

入参：经核验字段要求的缺陷属性（至少类型 + 等级/程度）+ `rule_version`。  
成功：唯一表项、分值、出处。不唯一：`AMBIGUOUS_MAPPING` 与候选。

#### `calculate_index`

入参：`calculation_type`、`rule_version`、标准化 `parameters`、`idempotency_key`。  
成功：`result_id`、`formula`、`parameter_trace[]`、`intermediate_steps[]`、`value`、`grade`、`recommendation`、`evidence[]`、`input_hash`。  
失败：`error_code`、`message`、`missing_or_invalid_fields[]`、`retryable`；失败响应不得含数值结果。  
同键重试返回同一 `result_id`；改输入须新步骤与新键。

#### `plot_curve`

入参：

| 字段 | 说明 |
|---|---|
| `result_ids` | 同一批次已有计算结果 ID 列表 |
| `x_axis` | 自变量名（如 `K`、`T`） |
| `y_axis` | 因变量名（如 `RI`） |
| `fixed_parameters_summary` | 固定参数摘要（展示用） |
| `rule_version` | 须与计算批次一致 |

成功：`resource_id`、坐标点、`x_axis` / `y_axis`、`rule_version`。只绘制已有结果，不估算缺失点。  
过渡期若仍返回 `png_base64`，须同时给出 `resource_id`；Phase 2 后禁止仅 Base64。兼容旧入参名 `axis` 仅当其等于 `x_axis` 时接受。

旧名 `calculation_id` / `chart_asset` 视为 `result_id` / `resource_id` 的别名，新实现只写后者。

## 4. 错误码

| 错误码 | 含义 | Agent 行为 |
|---|---|---|
| `MISSING_PARAMETERS` | 必填参数缺失 | 结构化追问；不调用计算器 |
| `AMBIGUOUS_MAPPING` | 无法唯一映射 | 展示候选项并澄清 |
| `INVALID_PARAMETER` | 类型、单位或范围非法 | 说明合法格式；不重试 |
| `RULE_NOT_PUBLISHED` | 规则未发布 | 停止计算 |
| `EVIDENCE_NOT_FOUND` | 无规程证据 | 章程固定拒答 |
| `TOOL_TIMEOUT` | MCP 超时 | 用原幂等键有限重试；展示失败与恢复 |
| `TOOL_UNAVAILABLE` | 工具不可用 | 保留输入与计划；条文检索仍可用 |

SSE / HTTP JSON 中的 `code` 必须使用上表字面量（大写）。

## 5. 未决项

- RI/MI 全量字段、依赖图、单位与值域的最终审核签字（相对原 PDF）。
- 管段选择 UI 与参数撤回交互细节。
- 图表目录的备份/清理运维节奏（逻辑 `resource_id` 已冻结）。
