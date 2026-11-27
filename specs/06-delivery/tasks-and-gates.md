# 05 实施任务与交付门禁

状态：Draft  
原则：按依赖顺序实施；每项任务先关联 Spec/验收场景，采用 TDD 先写测试、再实现、再重构，产出可审查的实现或文档。这里是计划，不代表任务已经完成。

| ID | 阶段 | 工作项 | 依赖 | 完成条件 |
|---|---|---|---|---|
| T01 | 规程基线 | 固定 PDF 哈希，登记页序/印刷页码和章节目录 | 无 | Source Manifest 可复现 |
| T02 | 规程基线 | 抽取术语、检测方法条件、周期、检查井和安全相关条款 | T01 | 按 `02-requirements/product-requirements.md` 指定条款逐项对照原件，记录审核状态 |
| T03 | 规程基线 | 抽取缺陷分值、RI/MI 公式、参数表、等级及处置建议并双审发布 | T01、rule-dual-review | worksheet + A/B 审签 + `validate_rules` 通过并进入 `rules/published/`；见 `04-development/rule-dual-review.md` |
| T04 | 规格 | 冻结槽位、接口、规则版本与九题行为 | T02、T03 | 编码前契约已写入：`03-design/calculation-rules.md` §7.0 夹具策略、`03-design/interfaces.md` SSE/错误码/图表与 `missing_parameter_groups`、`05-testing/agent-eval-tdd.md` 动作映射与双文件/CI 范围；题 9 领域仍依赖 T03 |
| T13 | RAG V1 入库 | 实现 Web 导入、DocMind 产物复用、LlamaIndex 切片/embedding、Chroma 持久化、SQLite metadata、预览、审核与索引版本 | rag-ingestion、KN-07 | ING-01 至 ING-09 可验收；现有 CJJ DocMind JSON 能写入并 reload；原文 PDF 页码/layout metadata 可追溯；pending_review 不可召回 |
| T05 | 知识检索 | 基于 V1 索引实现条款模型、BM25/向量召回、候选合并去重、reranker 重排及引用 UI/API；不使用 RRF | T02、T13、KN | 标注查询可验证召回、重排、来源页码；最终证据只含 `approved` 内容 |
| T06a | 检索归属 | 将 `search_clauses` 从 MCP 挪到主项目进程内；MCP 离线时条文问答可用 | T05、interfaces | **已落地骨架**：`dialogue.search_clauses` 进程内；MCP 工具列表无检索；Compose 不硬依赖 mcp |
| T06 | MCP | 独立交付 `pipe-assessment-mcp`：Schema、缺陷查分、RI/MI、绘图；自有存储与幂等；不含检索 | T03、T04、T06a | **同仓包已建**（`python -m pipe_assessment_mcp`，自有 `MCP_DATA_DIR`）；规则双审与独立镜像/仓仍待 T03 |
| T14 | Agent 评测 | 按 `05-testing/agent-eval-tdd.md` 冻结 `agent_cases.json`（L0/L1/L2）并实现 `agentEval/run.py`；先红灯 | T04、agent-eval | L0 与第 7/8 题用例可跑出失败报告；与 Web 入口约定写清 |
| T07 | Agent | 实现意图分类、受控计划、槽位追问及图状态恢复 | T04、T05、T06、T14 | `agent_cases` 目标子集变绿；缺参调用计数为零 |
| T08 | Web | 实现对话、条款、计划和工具日志、追问表单，并接入知识库导入与审核页 | T05、T07、T13 | WEB 场景通过；文件来源、切片/embedding 配置、审核和索引任务状态可见 |
| T09 | Web | 接入曲线显示、图/CSV 下载和九题快捷入口 | T06、T08 | 曲线点值与工具结果一致，快捷入口不绕过流程 |
| T10 | 交付 | 组织九题真实运行答卷、截图和现场演示脚本 | T05-T09 | 每题条款、版本、会话和必要日志完整 |
| T11 | 发布 | Compose 启动、初始化、健康检查、失败恢复说明 | T05-T09 | 干净环境按 README 可重复启动演示 |
| T12 | 发布 | 按实际运行结果编写自查说明 | T10、T11 | 如实列能力边界、缺陷、失败策略、智能问数边界和后续优化 |

## 开发门禁

1. T02/T03 完成前，不发布条款事实或计算规则到演示知识库/计算器；T03 按 `../04-development/rule-dual-review.md` 执行，禁止夹具进 published。
2. T04 完成前，不冻结 API 参数，也不静态硬编码“全部必填项”。
3. T07 完成前，工具只能由确定性节点按白名单调用；Agent 不得任意重试。
4. T10 的截图必须来自候选版本真实会话；不得伪造成功日志、计算值和曲线。
5. T12 只记录已经观察/验收的能力，缺陷和限制保持可见。
6. 每个实现项先补对应需求 ID/Spec 场景的测试；新测试先失败，再实现到通过，重构后重跑相关回归测试。
7. 计算、槽位校验、拒答和引用等确定性规则使用固定输入测试；Agent 集成测试用可控模型/MCP 替身，避免测试结果依赖外部服务或随机生成。
