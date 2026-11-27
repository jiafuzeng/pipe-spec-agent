# 计算规则目录（T03 双审）

规范：`specs/008-rule-dual-review.md`。操作摘要：`CHECKLIST.md`。

| 子目录 | 用途 | `rulebook` 会加载？ |
|---|---|---|
| `worksheets/` | `draft_rules --write` 的待审稿 | 否 |
| `reviews/` | 审核人 A/B 签字记录 | 否 |
| `published/` | 双审 + `validate_rules` 通过后的包 | 是（`status=approved`） |

```bash
.venv/bin/python -m rag.draft_rules RI --write
.venv/bin/python -m pipe_assessment_mcp.validate_rules path/to/candidate.json
# 通过后：
cp path/to/candidate.json pipe_assessment_mcp/rules/published/RI.json
```

禁止把 `agentEval/fixtures` 或 `fixture_only` 包放入 `published/`。