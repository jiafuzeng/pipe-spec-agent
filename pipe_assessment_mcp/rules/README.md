# 计算规则目录（T03 双审）

规范：`specs/04-development/rule-dual-review.md`。操作摘要：`CHECKLIST.md`。

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
题 9 的 RI 待审稿包含 paired_defect_rules。该段记录双缺陷净距界限与权重、叠加上限、管径表、土质列及独立算例。发布前须核对这些字段与相应页序。缺陷查分包与 RI 包须使用同一发布版本。原始记录传入 calculate_index 后，服务重新查表并比对题给分值，返回分组、S/Smax/F 和 E 的依据。单项领域测试不改变 published 状态或 AG-T09 的门禁。
