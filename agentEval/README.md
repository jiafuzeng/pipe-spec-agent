# agentEval

按 `specs/007-agent-eval-tdd.md` 做 Agent 层 TDD。执行器调用与 Web 相同的 `rag.web:app` 入口。

## 命令

```bash
# CI：ci=true 用例（默认进程内 MCP + 必要时 RULE_FIXTURE）
MCP_INLINE=1 EVIDENCE_LLM_VERIFY=0 .venv/bin/python -m agentEval.run --suite ci

# 全部（含非 CI；题 9 等 blocked 会 skip）
MCP_INLINE=1 RULE_FIXTURE=1 .venv/bin/python -m agentEval.run --suite all
```

报告写到 `agentEval/last_report.json`，也可通过 `GET /api/v1/evaluations/agent` 读取。

## 文件

| 文件 | 作用 |
|---|---|
| `agent_cases.json` | 唯一机器契约 |
| `agent_validation.json` | 题面与人工 acceptance |
| `fixtures/rules/` | `RULE_FIXTURE=1` 夹具 |
| `run.py` | 执行器与判分 |

## 门禁

1. 先红灯再实现（当前执行器已能出报告）。  
2. 夹具变绿须标 `rule_mode`；正式包走 `008` 双审。  
3. 禁止另写一套对话逻辑。
