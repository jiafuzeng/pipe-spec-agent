# 计算规则双审操作清单

完整规范见 `specs/04-development/rule-dual-review.md`。

## 每次发布前

1. 确认 PDF：`rag.source.PDF_SHA` 与原文文件一致  
2. 生成/更新 worksheet：`python -m rag.draft_rules RI --write`（或 MI / defect_score）  
3. 审核人 A、B 各建一份 `reviews/YYYYMMDD-<kind>-<姓名>.md`，对照 PDF 勾选 008 §4  
4. 合并审签字段到候选 JSON（`reviewers` ≥ 2、`reviewed_at`、算例）  
5. `python -m pipe_assessment_mcp.validate_rules <候选.json>`  
6. 通过后复制到 `published/`（禁止放入 `fixture_only` 包）

## 禁止

- 把 `agentEval/fixtures` 拷进 `published/`  
- 一人签两个名  
- 未跑 validate 就改 `status=approved` 并上演示  
