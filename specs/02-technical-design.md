# 技术设计

## 1. 技术选型

| 层次 | 选择 | 理由 |
| --- | --- | --- |
| 语言 | Python 3.11+ | 计算、绘图、MCP 和 API 在同一语言里测试 |
| 前端 | 独立的 React 应用（`frontend/`） | 页面、样式和浏览器状态不进入 API 进程。开发时由 Vite 提供，部署时由 nginx 提供 |
| API | FastAPI，只提供 HTTP 接口 | 会话、导入、审核和健康检查走 `/api` 与 `/health`。API 不返回页面 |
| 编排 | LangGraph 单图 | 一项任务怎么走：拆目标、校验步骤依赖、部分完成和跨轮恢复。Web 与 agentEval 共用同一执行入口 |
| 工具层 | 独立交付物 `pipe-assessment-mcp`（FastMCP，Streamable HTTP） | 按哪个已发布规则版本算出什么结果。主项目只保留客户端；计算服务有自己的启动命令、镜像、依赖、存储和测试 |
| RAG 入库与检索 | LlamaIndex `IngestionPipeline` + `SentenceSplitter` / `MarkdownNodeParser` + Chroma 持久化 + BM25 + reranker | Web 可选择切片和 embedding profile；源文档、DocMind layout、页码及版面 metadata 随 node 保存；BM25 与向量候选合并去重后直接由 reranker 重排，不使用 RRF |
| Embedding | LlamaIndex Ollama / DashScope integrations；profile 由服务端注册表配置 | Web 只选择已配置模型，不接触凭证；模型 ID、版本、维度与索引版本绑定，改模型必须重建向量 |
| 模型 | OpenAI 兼容 HTTP 接口，地址和密钥放在环境变量 | 模型只做意图、槽位抽取、规划和行文。换模型不改计算 |
| 数值 | `decimal.Decimal` | 等级边界用精确值比较 |
| 绘图 | Matplotlib 输出 PNG | 图片由工具生成，界面直接显示 |
| 测试 | pytest | 计算、槽位和检索在接入模型之前就有确定结果 |

不把公式写进提示词后让模型运算。提示词只描述何时调用哪个工具。

## 2. 两个交付物、三个进程

V1 定为两个独立交付物、三个运行进程。本轮只确定契约，不调整现有代码目录。

| 交付物 | 进程 | 职责 |
| --- | --- | --- |
| `pipe-spec-agent` | React 前端 | 页面、样式和浏览器状态。开发时由 Vite 提供，部署时由 nginx 提供 |
| `pipe-spec-agent` | FastAPI 应用 | 会话、知识导入与审核、评测报告、LangGraph 编排、RAG 检索，以及代读图表资源 |
| `pipe-assessment-mcp` | 远程 MCP 服务 | 发布计算工具、规则包和图表资源。其他客户端可以不经过主项目单独调用 |

LangGraph 负责一项任务怎么走，RAG 负责规程依据在哪里，MCP 负责按哪个规则版本算出什么结果。

```
浏览器
  └─ React 前端
       └─ /api
            └─ FastAPI（main:app）
                 ├─ routes：sessions / knowledge / evaluations
                 ├─ LangGraph（app/agent/workflow.py）
                 ├─ RAG（app/rag/retrieval.py）
                 └─ MCP 客户端（app/integrations/mcp_client.py）
                      └─ pipe-assessment-mcp
```

主应用启动时可以检查 MCP 连通性，但计算服务离线不阻止 FastAPI 启动。文档导入和规程检索不依赖计算服务。`/health` 区分「应用可用」和「远程计算能力暂不可用」。

### 2.1 项目目录结构

本轮只定目标结构，不调整现有代码目录。查表与公式留在 `pipe-assessment-mcp`，不复制进编排器。

```
pipe-spec-agent/                    # 项目一：规程问答应用
├── main.py                        # FastAPI 入口，导出 app
├── app/
│   ├── server/
│   │   ├── application.py         # 创建 FastAPI、注册路由、管理生命周期
│   │   └── routes/
│   │       ├── sessions.py        # 会话、消息、SSE
│   │       ├── knowledge.py       # 文档导入、审核、索引管理
│   │       ├── evaluations.py     # RAG / Agent 评测报告
│   │       └── health.py
│   ├── agent/                     # 规划、状态、追问、工具编排、回答
│   ├── knowledge/                 # 文档生命周期与审核
│   ├── rag/                       # 切片、检索、重排、证据定位
│   ├── integrations/
│   │   └── mcp_client.py          # 连接外部 MCP、调用工具、转换错误
│   └── config.py
├── frontend/
├── ragEval/
├── agentEval/
├── tests/
├── Dockerfile
└── compose.yaml                   # 部署问答应用和前端

pipe-assessment-mcp/               # 项目二：可被多个应用使用的管道评估工具服务
├── pyproject.toml                 # 包、依赖、启动命令和服务版本
├── src/pipe_assessment_mcp/
│   ├── server.py                  # MCP 入口，注册工具、启动服务
│   ├── tools/
│   │   ├── schema.py              # 查询计算参数和规则版本
│   │   ├── defects.py             # 缺陷查分
│   │   ├── indices.py             # RI / MI 计算
│   │   └── charts.py              # 根据计算结果绘图
│   ├── domain/                    # 规则校验、公式、分档和计算逻辑
│   ├── storage/                   # 计算结果、幂等记录、图表存取
│   └── config.py
├── rules/                         # 独立发布的规则包、出处、审核记录
├── tests/                         # 工具协议测试、计算算例、边界测试
├── Dockerfile
└── README.md
```

关键入口约定：

| 位置 | 职责 |
| --- | --- |
| `main.py` | 导出 FastAPI `app`。本地和容器统一使用 `uvicorn main:app` |
| `app/server/application.py` | 创建应用、注册路由、管理资源生命周期。测试通过同一工厂启动，并可替换模型、存储或 MCP 客户端 |
| `app/server/routes/` | 校验 HTTP 请求并输出 JSON 或 SSE |
| `app/agent/` | 创建或恢复一次 Agent 执行。Web 和 `agentEval` 共用该入口 |
| `app/rag/` | 在指定索引范围内检索证据。Agent 使用已发布索引，`ragEval` 可显式指定待审索引 |
| `app/integrations/mcp_client.py` | 连接外部 MCP，调用工具并转换错误。地址、认证和超时只从后端配置读取 |
| `pipe-assessment-mcp` | 拥有独立启动命令、镜像、依赖、`rules/` 和测试 |

问答应用侧数据：

```
data/knowledge/      # 权威：originals、parsed、registry.sqlite、Chroma
# 已删除主仓 kb/；发布规则在 pipe-assessment-mcp/rules/；评测夹具在 agentEval/fixtures/rules/
```

查找解析产物顺序见 `006` §3.3。不再把 `kb/clauses.jsonl` / `kb/index/` 当作 V1 必建路径。

## 3. 一项任务如何执行

V1 使用 LangGraph 单图，步骤类型有限。LLM 可以拆分目标、提取参数、改写检索子问；编排层验证步骤依赖和执行条件。首版业务动作只有五种：查依据、核对证据、补参数、调用计算、生成图表。

允许一轮部分完成。每个结论绑定自己的证据。一支失败时，另一支仍交付已有结果。例如第 5 题拆成三个检索子问，缺少已审核证据的子问单独标为待确认，不取消另外两个有依据的回答。

以「解释 RI 公式，再固定其他参数画 K 的曲线」为例：

| 阶段 | 系统动作 | 缺项或失败时 |
| --- | --- | --- |
| 理解本轮 | 识别解释公式和生成曲线两个目标，提取用户明确给出的 K | 同一字段出现冲突值时保留来源并追问 |
| 并行准备 | RAG 检索公式和分档；MCP 返回当前已发布规则的参数要求 | 一支失败，另一支仍交付已有结果 |
| 核对条件 | 按管段读取已确认的 F、E、T，检查单位、规则版本和取值条件 | 返回已核验的公式说明，一次问齐缺项，并保存曲线任务 |
| 恢复计算 | 用户补齐参数后，对每个 K 值建立独立计算步骤 | 已成功的点保留结果 ID，只重试未完成的点 |
| 绘图交付 | 用本批次结果 ID 生成曲线，返回坐标、固定参数和依据 | 绘图失败时仍展示计算表；重试绘图复用原结果 |

条文结论只使用本次检索到的条款。计算数字必须能在同一次工具返回中找到，对不上就删去并说明未能核对。规划日志和 MCP 日志随回答返回，结构见 `04-interfaces.md`。

### 3.1 五个标识

一条用户消息和一项跨轮任务不是同一个东西。

| 标识 | 表示什么 | 生命周期 |
| --- | --- | --- |
| `session_id` | 一次对话 | 可以讨论多个管段 |
| `subject_id` | 当前管段 | 管径、土质、缺陷等已确认事实归属于它 |
| `turn_id` | 一条用户消息及本轮反馈 | 用户每次发送消息产生一个 |
| `run_id` | 一项可跨轮推进的任务 | 第一轮提出画图，第二轮补参数，继续同一个 run |
| `step_id` | 一次检索、计算或绘图步骤 | 用于依赖、重试、审计和恢复 |

每个已确认参数记录值、单位、来源消息、所属管段和确认状态。每个计算步骤记录输入快照、规则版本、执行状态、幂等键和结果 ID。LangGraph checkpoint 保存执行位置；业务存储保存用户确认过的事实和工具结果。V1 可以共用一个 SQLite 实例，分别使用各自的表。

两个常见场景：

- 「刚才说错了，管径是 1200 mm。」更新当前管段的管径，使依赖旧管径的派生参数、计算和图表失效。其他已确认参数继续复用，旧结果保留供追溯。
- 「换另一段管，按刚才的方法再算。」新建或切换 `subject_id`，复用计算流程，重新确认新管段需要的事实。「按刚才的」指方法还是参数有歧义时，由 Agent 追问。

同一管段的两条消息可能几乎同时到达。V1 按 `session_id` + `subject_id` 串行更新状态，并为状态增加版本号，防止较早的计算回写覆盖用户刚做的修正。

## 4. 检索

建库与切片按 `006-rag-ingestion-v1.md`：DocMind layout / Markdown → LlamaIndex → Chroma + registry；不在回答时临时 OCR。`kb/clauses.jsonl` 不是 V1 运行时权威语料。

1. 活动索引只含人工审核通过的 nodes；条款号形态如 `1.0.1`、`表8.3.4-1`。
2. 按规程版本、章节、内容类型等元数据过滤；条款号/表号优先精确匹配。普通查询并行 BM25 与向量召回。
3. 合并去重后由 reranker 重排，截取 top-k；返回条款、原文、页码、分数与命中来源。
4. 编排器只使用本次命中证据组织句子；无命中则用章程固定拒答。
5. 候选数量、top-k 与阈值由 `ragEval` 标注集标定。

分值、K、E、T、等级阈值不走「从 OCR 读数」，走 MCP 已发布规则包（目标在 `pipe-assessment-mcp/rules/`）。主仓不再保留 `kb/` 草稿。规则双人审核与参考算例是 T03 完成条件。

## 4.1 文档导入与向量索引 V1

Web 上传原始 PDF 时，后端复用 DocMind 生成 JSON/Markdown；已有 `data/docmind/{document_id}/document.json` 时优先使用 JSON 中的 `Data.layouts`，避免重复解析。原始文件以 SHA-256 标识并保存为不可变版本。具体格式、API、metadata、切片配置、预览和验收场景见 `006-rag-ingestion-v1.md`。

LlamaIndex `Document`/Node Parser 负责将已清洗的结构块切成 nodes，`IngestionPipeline` 将所选 embedding integration 生成的向量写入本地 Persistent Chroma。默认结构优先切片，chunk size 512 tokens、overlap 64。可选策略见 `006-rag-ingestion-v1.md`：句子、Token、Markdown 标题、句子窗口、层次、语义和语义双合并。SQLite 保存导入任务、审核状态、原文元数据和索引版本；原文 PDF/DocMind 文件留在 `data/knowledge`。

每个 node 和 Chroma collection 都绑定 `source_doc_id`、原文 SHA、PDF 页序、章节/条款、DocMind layout ID、切片配置哈希、embedding profile/model version/dimension、review status。行政元数据可过滤但不参与 embedding 文本；页码和条款不可从缺失数据中推断。新导入内容默认 `pending_review`，向量检索按 `approved` metadata 过滤。索引使用 staging collection，完整成功后才注册为可用版本；失败不覆盖已有活动索引。

## 5. 智能问数与记忆

槽位是结构化字段，不是一段自由摘要。字段定义、必填组合和追问文案的数据来源见 `04-interfaces.md`。

抽取由模型完成，结果必须通过模式校验：管径是正数，K 只能是 0、3、6、10，T 只能是表 8.3.4-3 中出现的值，缺陷必须带名称或代码以及等级或分值。校验失败则忽略该字段并继续追问，不把模糊词写成一个数。

「流砂」这类表中不存在的土质名称，记录为未匹配，并向用户展示表中的列名。不写入 T。

界面用标签显示已确认槽位。用户说「把管径改成 800」时只替换管径，并清除由旧管径推出的 E，下次计算时重新查表。

## 6. 方案规划

方案题的规划步骤固定为：

1. 检索候选方法的约束条款（电视、潜望镜、声纳、人员进入、潜水、检查井先后、联合检测）。
2. 把用户已给事实填进约束：管径、水位或充满度、水深、能否降水、积泥。
3. 对每条「不得 / 应 / 不宜」给出满足、不满足或信息不足。
4. 信息不足且会改变「满足 / 不满足」时，先追问。
5. 在已确定的约束下安排顺序：检查井在管道检测之前（第 9.0.1 条）；一种方法不能反映全面状况时采用联合检测（第 3.0.3 条）；声纳轮廓图不作为结构性缺陷的最终依据（第 5.4.5 条）。

不输出规程没有的设备型号和停水时限。

## 7. 失败处理

| 情况 | 行为 |
| --- | --- |
| MCP 离线或超时 | 应用和检索保持可用。计算步骤返回明确的工具状态；接收结果前超时则用原幂等键重试一次，MCP 返回已有结果。用户改了输入才新建计算步骤 |
| 工具参数校验失败 | 把工具返回的缺失或非法字段转成追问 |
| 查表未命中 | 返回候选行，由用户选定。不取最相近的一行 |
| 检索无命中 | 固定拒绝语句 |
| 模型输出了工具结果中没有的数字 | 删去该数字，保留已核对部分 |

这些行为写进自查说明的「失败策略」一节，并在测试里至少覆盖超时和未命中各一次。

## 8. 界面

页面由独立前端提供。FastAPI 不挂载页面，也不把构建产物打进 API 镜像。浏览器只打开前端地址。前端以相对路径请求 `/api`；开发服务器和前端容器把该路径转到 API，因此页面与接口可以分别构建、分别启动。直接从另一个源站调用 API 时，API 按 `CORS_ORIGINS` 放行来源，默认包含本机前端开发地址。

单页三区：对话、规划与 MCP 日志、当前槽位。计算得到的 PNG 显示在对应回答下方，并提供原图链接。演示分辨率以笔记本浏览器全屏为准。

界面不提供「关闭日志」的开关。

## 9. RAG 与 MCP 的工具契约

| 工具 | 归属 | 关键输入 | 关键输出 |
| --- | --- | --- | --- |
| `search_clauses` | 主项目 RAG | 子问题、查询范围、Top K | 证据 ID、原文、条款或表号、PDF 页序、来源版本 |
| `get_calculation_schema` | MCP | RI、MI 或查分类型 | 已发布规则版本、字段、单位、条件必填项、出处 |
| `lookup_defect_score` | MCP | 缺陷类型、等级、规则版本 | 表项分值、出处，或需要澄清的字段 |
| `calculate_index` | MCP | 标准化参数、固定规则版本、幂等键 | 结果 ID、输入快照、中间量、指数、等级、建议和出处 |
| `plot_curve` | MCP | 同一批次的结果 ID、自变量 | 图表资源 ID、坐标点、坐标轴、固定参数摘要 |

跨服务约定：

1. 一次任务固定规则版本。获取 Schema 后，查分、计算和绘图沿用该版本。补参期间规则升级时，服务继续支持旧版本，或明确要求重新核对参数，不静默切换。
2. 重试使用稳定幂等键。主项目在调用前持久化步骤和幂等键。MCP 已算完但主项目未收到结果时，重试返回已有结果。用户改了输入后才创建新的计算步骤。
3. 跨服务用证据标识关联。MCP 返回规程版次、原 PDF 哈希、条款或表号及页序，主项目据此关联本地 RAG 证据。图表使用资源 ID，由主项目后端读取并转给前端。浏览器不接触 MCP 凭证或容器路径。

原始缺陷到指数参数的推导由 MCP 的领域计算层负责，包括分组、系数选择以及 S、Smax、F 的推导，并逐项返回依据。Agent 只负责识别「两处、各 5 分、间距 1.2 m」这类事实，并处理「流砂」这类歧义。重要计算规则只有一个实现。

## 10. HTTP 与前端事件

保留现有知识接口，新增能力放在对应资源下。

| 接口 | 用途 |
| --- | --- |
| `POST /api/v1/sessions` | 创建会话 |
| `POST /api/v1/sessions/{sid}/turns` | 提交消息。沿用 SSE，首个事件返回 `turn_id` 和 `run_id` |
| `GET /api/v1/sessions/{sid}` | 刷新后恢复消息、当前管段、已确认参数和待回答问题 |
| `GET /api/v1/runs/{run_id}` | 查询步骤、状态、工具结果及失败原因 |
| `GET /api/v1/runs/{run_id}/events` | 断线后从最后收到的事件序号续读 |
| `GET /api/v1/artifacts/{resource_id}` | 经主项目读取本次任务产生的图表 |
| `/api/v1/knowledge/...` | 沿用文档导入、预览、审核和删除 |
| `/api/v1/evaluations/...` | 获取 RAG 或 Agent 评测报告 |

前端保留 `plan_step`、`tool_call`、`clarification_required`、`answer`、`chart`、`error`，并统一带上 `run_id`、`step_id` 和递增的 `event_id`。断开连接只停止接收事件，不取消已在执行的步骤。以后若增加「停止执行」，由显式取消接口停止后续步骤。刷新页面不丢掉已经完成的曲线点。

## 11. 架构是否成立

| 验收场景 | 观察什么 |
| --- | --- |
| 主项目单独启动，MCP 离线 | 文档导入、检索和条文问答可用；计算请求返回明确的工具状态 |
| MCP 单独部署，使用独立测试客户端 | 无需主项目数据库、源码或会话，即可查 Schema、查分、计算和绘图 |
| 第 5 题跨章问答 | 三个子问题分别检索；每个结论能定位到对应条款或表格 |
| 第 7 题分两轮完成 | 首轮解释公式并追问，次轮恢复同一任务，固定参数与四个图表点一致 |
| 第 9 题出现土质歧义 | 保留已明确的缺陷与管径，追问土质映射；未确认前没有 RI 结果 |
| 工具已执行成功但响应丢失 | 重试复用结果；日志能说明该步骤执行了几次请求、生成了几个实际结果 |

落地顺序是先定契约，再换编排框架。第一阶段抽离 MCP，跑通「独立客户端 → 计算 → 取图」。第二阶段整理 `main.py`、路由和业务目录，保持现有前端及 `ragEval` 可用。第三阶段用 LangGraph 接管对话，优先打通第 7 题的两轮流程。出现回归时，分别定位服务拆分、应用重构或 Agent 编排。

## 12. 对照当前代码的交付补充

当前仓库仍以 `rag/` 为主应用入口（`uvicorn rag.web:app`），会话在内存里；计算侧已拆为同仓包 `pipe_assessment_mcp`（检索已出 MCP）。下面其余事项若不补齐，按第 11 节验收仍会卡住。

### 12.1 从现有代码迁到目标目录

| 现有位置 | 目标位置 | 过渡约定 |
| --- | --- | --- |
| `rag/web.py` | `main.py` + `app/server/application.py` + `routes/knowledge.py` + `routes/health.py` | **入口切换**：Phase 1–2 默认仍 `uvicorn rag.web:app`；`main:app` 在会话/SSE/artifacts 齐备且导入/ragEval 不回归后切换；README 与 Compose 同步改一行命令。过渡期可双入口同图，禁止两套对话逻辑 |
| `rag/dialogue.py` | `routes/sessions.py` + `app/agent/` | Web 与 `agentEval` 必须走同一入口；禁止评测另写简化对话 |
| `rag/search.py` / `pipeline.py` / `source.py` / `registry.py` | `app/rag/`、`app/knowledge/` | 切片与检索留在主项目；不搬进 MCP |
| `rag/mcp_server.py` + `rag/calculation.py` | 独立仓 `pipe-assessment-mcp` + `rules/` | MCP 不再依赖主项目 `Registry`、Chroma 或 DocMind；主仓已去掉 `kb/` |
| `ragEval/`、`frontend/` | 同名目录保留 | 路由改名时提供别名，避免前端和评测脚本同时大改 |

### 12.2 工具归属必须改

已落地：`pipe_assessment_mcp` 独立包（`python -m pipe_assessment_mcp`）；工具列表无 `search_clauses`；`dialogue.search_clauses` 进程内调用；MCP 自有 `MCP_DATA_DIR` 存结果与图表；Compose 中 backend 不再 `depends_on: mcp`。

约定（持续）：

1. `search_clauses` 只在主项目进程内调用，不再注册为 MCP 工具。
2. MCP 只保留 `get_calculation_schema`、`lookup_defect_score`、`calculate_index`、`plot_curve`。
3. `04-interfaces.md` 已改为唯一契约：检索在主项目，MCP 仅计算/绘图；旧 MCP 客户端升级时按破坏性变更记录。

### 12.3 健康检查与 Compose

当前 `/health` 只返回 `{"status":"ok"}`，`compose.yaml` 里 `backend.depends_on: [mcp]`。

约定：

1. `/health` 至少区分：`app`、`registry`、`embedding`、`mcp`。应用可用时顶层可为 `ok`；MCP 不可达时 `mcp.status=unavailable`，不拖垮导入和检索。
2. Compose 中 `backend` 不硬依赖 `mcp` 就绪；MCP 以可选侧车部署。
3. API 镜像与 MCP 镜像分开：MCP 镜像不含 DocMind、Chroma、前端构建；规则包只进 MCP 镜像。

### 12.4 会话与标识落地

当前只有内存 `sessions` 和可选 `subject_id`，SSE 没有 `turn_id` / `run_id` / `step_id` / `event_id`，也没有 `GET /sessions/{sid}`。

约定：

1. V1 业务表至少包括：`sessions`、`subjects`、`turns`、`runs`、`steps`、`run_events`、已确认参数、工具结果引用。可与知识库 `registry.sqlite` 同实例、分表，或单独 `app.sqlite`。
2. 首个 SSE 事件必须带 `turn_id`、`run_id`、`event_id=0`；后续事件递增 `event_id`，并带 `step_id`（适用时）。
3. 实现 `GET /api/v1/sessions/{sid}`、`GET /api/v1/runs/{run_id}`、`GET /api/v1/runs/{run_id}/events?after_event_id=`。断线只停接收；未取消的 run 继续执行，事件可续读。
4. 单 worker 仍可接受，但同一 `session_id + subject_id` 的回合必须串行；状态带 `state_version`，过期回写拒绝。

### 12.5 MCP 协议与存储边界

当前计算幂等表写在知识库 SQLite，`plot_curve` 直接返回 `png_base64`，`get_calculation_schema` 未强制 `rule_version`，规则包多为 `pending_review`。

约定：

1. MCP 自有存储保存结果、幂等记录和图表文件；主项目只存 `result_id` / `resource_id` 引用。
2. `plot_curve` 返回 `resource_id`；主项目 `GET /api/v1/artifacts/{resource_id}` 代读。SSE 的 `chart` 事件只带资源 ID，不塞整图 Base64。
3. 一次 run 在首次 `get_calculation_schema` 后锁定 `rule_version`；后续查分、计算、绘图必须传同一版本。
4. 主项目在调用前持久化 `(step_id, idempotency_key)`；超时用原键重试一次。当前每次 `uuid4` 的做法不满足「响应丢失可复用结果」。
5. 生产计算开关默认关闭，直到至少一份 RI 规则包完成双人审核并标记 `approved`；未发布时返回 `RULE_NOT_PUBLISHED`，不返回数值。
6. **评测夹具**：仅当 `RULE_FIXTURE=1`（或等价环境变量）时，进程可加载 `agentEval/fixtures/rules/` 最小 RI 包，供 `fixture_rules=true` 用例；夹具不得写入演示发布态，报告须标 `rule_mode=fixture`。细则见 `03-calculation.md` §7.0。
7. Compose：`backend` **不得** `depends_on: mcp` 作为硬依赖；MCP 为可选侧车，`/health.mcp` 可为 `unavailable`。

### 12.6 缺陷推导与规则数据

主仓已删除 `kb/`；`calculation.py` 仍是简化加权，不足以覆盖第 9 题；缺陷空间分组尚未接入。

约定：

1. 缺陷分组、系数选择、S / Smax / F 推导放在 MCP `domain/`，并逐项返回依据。
2. 已发布规则只存在于 MCP `rules/`（或 `RULES_DIR`）；评测用 `RULE_FIXTURE=1` + `agentEval/fixtures/rules/`；主项目不放草稿规则包。
3. Agent 识别「两处、各 5 分、间距 1.2 m」等事实；「流砂」等歧义只追问，不写死映射。

### 12.7 Agent 能力缺口

当前对话是正则分支，不是五种业务动作；没有真正的复合子问拆分、槽位 Schema 校验和参数失效规则。

约定：

1. Phase 0 可暂时保留 `dialogue.py` 作为对照基线；Phase 3 用 LangGraph 替换后，基线仅用于回归对比，不再服务 Web。
2. 五种动作各自产出可观察事件；第 5 题必须拆成多个检索 `step_id`，允许部分回答。
3. 槽位由模型抽取后经 Schema 校验；非法值不入库。改管径只清依赖旧管径的派生量与结果，其他已确认参数保留。
4. 「核对证据」默认用条款匹配 + 重排阈值；若继续用聊天模型复核，必须可关闭，且评测模式默认关闭。

### 12.8 前端与评测

当前聊天页无持久槽位栏，请求体不传 `subject_id`，刷新会新建会话；`agentEval/` 只有题集没有执行器；RAG 评测挂在 `/api/v1/knowledge/rag-eval`。

约定：

1. 对话区旁固定显示当前管段与已确认参数；切换管段走 `subject_id`。
2. `session_id` / 进行中的 `run_id` 写入浏览器本地；刷新后先 `GET session`，再按 `after_event_id` 续读。
3. `agentEval` 按 `007-agent-eval-tdd.md`：先定 `agent_cases.json`，再实现 `run.py`；调用与 Web 相同的 Agent 入口，报告供 `GET /api/v1/evaluations/agent` 读取。
4. `/api/v1/evaluations/rag` 兼容或迁移现有 `rag-eval`；前端评测页改走 evaluations 命名空间。

### 12.9 文档路径统一

当前同时存在 `data/document.json`、`data/docmind/...` 与 `data/knowledge/parsed/...`。

约定：权威导入路径以 `006-rag-ingestion-v1.md` 的 `data/knowledge/originals|parsed` 为准；仓库样例 `data/document.json` / `data/document.md` 仅作对齐页码的过渡输入，实现中写明查找顺序，避免三套路径并存无说明。

### 12.10 修正后的落地门禁

| 阶段 | 完成标准 |
| --- | --- |
| 1. 拆 MCP | 独立镜像可查 Schema / 查分 / 计算 / 取图；主项目检索不再经 MCP；MCP 离线时导入与条文问答可用 |
| 2. 应用整理 | `main:app`、健康分量、会话持久化、runs/events/artifacts 可用；现有 `ragEval` 与导入页不回归 |
| 3. LangGraph | 先让 `agentEval` L0/第7/8 题红灯变绿；五个标识进入 SSE；第 5 / 7 / 9 题按 `agent_cases` 验收；与 Web 共用入口 |

未完成第 12.5 条规则发布门禁前，现场演示可以走检索与导入，不得把未审核规则算成正式 RI/MI 结论。
