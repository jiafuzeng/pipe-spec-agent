# Implementation Plan: 会话管理

**Branch**: `010-会话管理` | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `.specify/specs/010-会话管理/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

规程问答页在工作台导航右侧增加一列历史会话。列表来自已有会话记录，按最近活动从新到旧排列，每条显示最近一次用户提问和活动时间。点开一段后，用该段已保存的提问和运行事件恢复聊天，并允许继续发送。上次打开的会话号只记在本机浏览器里；聊天正文仍以服务端为准。长期记忆不在本变更内。

## Technical Context

**Language/Version**: Python 3.11 及以上（当前工作台虚拟环境为 3.13）；问答页为现有 React 页面

**Primary Dependencies**: 现有 FastAPI、`app/agent/store.py` 的 SQLite 会话表、`frontend/src/Chat.jsx`。不新增数据库或前端框架。

**Storage**: 会话、提问和运行事件仍在 `AGENT_DB`（默认 `data/agent/app.sqlite`）。上次打开的会话号放在浏览器 `localStorage`。不把聊天正文再存一份到浏览器。

**Testing**: `unittest`。会话列表与单段隔离用 `tests/test_sessions.py`，`AGENT_MODEL_ENABLED=0`，不调用真实模型。页面左侧的排列和切换用浏览器按 [quickstart.md](quickstart.md) 核对。

**Target Platform**: 本机单工作台。页面 `http://127.0.0.1:5173/`，接口 `http://127.0.0.1:8000`。

**Project Type**: 本机 Web 工作台（已有 FastAPI 与 React 页面）

**Performance Goals**: 打开问答页时一次取回历史列表。单台工作台已有的几十到上百段会话能在当次打开中列完并滚动查看。

**Constraints**: 不改变规程拒答、计算和事件日志。等待回答时不能切换会话。读不到的会话不得显示成另一段的内容。不实现重命名、删除、搜索，也不改长期记忆。

**Scale/Scope**: 一台工作台、一个问答页。左侧一列历史会话，主导航里的导入文档和评测保持原位。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 门禁 | 计划前 | 设计后 |
| --- | --- | --- |
| I. 唯一知识源 | 通过。会话列表不新增知识，也不改无条款时的固定拒答。 | 通过。恢复聊天只重放已保存的提问和事件，不把历史回答写成新的规程依据。 |
| II. 计算不心算 | 通过。继续旧会话不重新心算，也不改工具归属。 | 通过。打开历史会话只读已有事件，不为此再调用计算器。 |
| III. 测试先行 | 通过。先改 `tests/test_sessions.py` 的列表顺序和隔离，再改页面。 | 通过。quickstart 把失败测试放在实现之前。 |
| IV. 双交付物边界 | 通过。会话仍在 `pipe-spec-agent`。MCP 不提供会话列表。 | 通过。契约只描述工作台自己的会话读取。 |
| V. 规则发布门禁 | 通过。本变更不加载规则包，也不输出正式 RI/MI。 | 通过。 |
| 会话与表达 | 通过。各段会话的已确认内容仍只属于该段。 | 通过。切换会话不把上一段的提问写入下一段。 |

无章程例外。

## Project Structure

### Documentation (this feature)

```text
.specify/specs/010-会话管理/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── session-history.md
└── tasks.md             # /speckit-tasks 再写，本命令不创建
```

### Source Code (repository root)

```text
app/agent/store.py                 # 历史列表：最近提问、最近活动时间、从新到旧
app/server/routes/sessions.py      # 沿用 GET /api/v1/sessions 与 GET /api/v1/sessions/{sid}
frontend/src/main.jsx              # 主导航保持不动
frontend/src/Chat.jsx              # 问答页左侧列表、打开、继续、上次打开
frontend/src/style.css             # 左侧列、单行截断、滚动
frontend/src/api.js                # 读取列表
tests/test_sessions.py             # 列表顺序、时间、单段消息隔离
```

**Structure Decision**: 文档只放在 `.specify/specs/010-会话管理/`。实现沿用现有会话表和问答页，不新建服务。工作台主导航留在 `frontend/src/main.jsx` 的侧栏；历史会话是问答页自己的左列，避免挡住导入和评测。

## Complexity Tracking

章程检查无例外，不单列。

## Phase 0 与 Phase 1 结论

研究结论见 [research.md](research.md)。会话、列表条目和聊天记录见 [data-model.md](data-model.md)。列表和打开会话的读取约定见 [contracts/session-history.md](contracts/session-history.md)。验收步骤见 [quickstart.md](quickstart.md)。

设计之后重新核对章程：历史列表和聊天恢复都不进入规程检索，也不触发新的计算。上次打开的会话号只是本机书签，丢失时退回空白新对话，不编造另一段的内容。
