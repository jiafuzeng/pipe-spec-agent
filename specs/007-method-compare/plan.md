# Implementation Plan: 检测方法对比与检测方案

**Branch**: `007-method-compare` | **Date**: 2026-11-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-method-compare/spec.md`

## Summary

比较题、方案题和「为何不能 / 检查先后」题目前都走条文摘录，没有按方法分段，也不会根据条款原文否决不满足条件的方法。本切片在现有会话回合里增加三类意图：比较、方案、解释。检索仍在进程内完成；数值界限只从本轮证据原文解析。不改计算追问，不发布 RI/MI 规则。

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: FastAPI（现有 `rag/dialogue.py` 回合）、现有进程内 `search_clauses`

**Storage**: 无新存储。会话仍为进程内字典。

**Testing**: unittest。`tests/test_answers.py` 用固定证据；`tests/test_dialogue.py` 用检索与 MCP 替身。

**Target Platform**: 本地演示的 FastAPI 进程

**Project Type**: web-service（已有 React 前端只展示回答文本，本切片不改页面结构）

**Performance Goals**: 与现有条文问答同一回合内返回，不新增模型调用

**Constraints**: 章程 I/II/V。无证据则固定拒答。不得心算指数。不得把未出现在原文中的百分数写进结论。MCP 计算工具调用数为零。

**Scale/Scope**: 九题中的题 2、题 4、题 5、题 6。不覆盖题 7–9 的计算与曲线。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 本计划 | 结果 |
| --- | --- | --- |
| I. 唯一知识源 | 结论只引用本轮证据；界限从原文解析 | 通过 |
| II. 计算不心算 | 这三类意图不调用计算或绘图 | 通过 |
| III. 测试先行 | 先写 `tests/test_answers.py` 与对话替身测试 | 通过 |
| IV. 双交付物 | 检索保持 `search_clauses` 进程内 | 通过 |
| V. 规则发布门禁 | 不读取、不发布计算规则 | 通过 |

Phase 1 之后复检：数据模型和契约没有引入新的知识源或计算器。通过。

## Project Structure

### Documentation (this feature)

```text
specs/007-method-compare/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/turn.md
└── tasks.md
```

### Source Code (repository root)

```text
rag/
├── answers.py          # 意图、比较、方案、解释的纯函数
└── dialogue.py         # 在非计算回合里调用上述纯函数

tests/
├── test_answers.py
└── test_dialogue.py
```

**Structure Decision**: 纯函数放在 `rag/answers.py`，对话只负责检索、SSE 和拒答。前端继续显示 `answer.text`，不新增接口字段。

## Complexity Tracking

无章程违规需要豁免。
