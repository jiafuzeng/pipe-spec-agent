# agentEval fixtures

仅在 `RULE_FIXTURE=1`（或执行器等价开关）时加载。夹具变绿 ≠ 规程已审核发布。

## 布局

```
fixtures/
├── README.md
├── rules/
│   └── RI.min.json          # 最小 approved 替身：复现 specs/03 §7.1 四点 RI
└── mcp/                     # 可选：offline / timeout / idempotent 替身响应（实现 run.py 时补）
```

## 约定

| 项 | 值 |
|---|---|
| `rule_version` | `CJJ181-2012-fixture-ri-7.1` |
| 公式 | `RI = 0.7×F + 0.1×K + 0.05×E + 0.15×T` |
| 基准固定参数 | F=6, E=6, T=0 → K∈{0,3,6,10} 得 4.5/4.8/5.1/5.5 |
| 生产路径 | 不得把本目录拷入演示 `approved` 发布态 |

`AG-T09` / 题 9 领域算例不在本夹具范围内（`blocked_until=T03_domain`）。
