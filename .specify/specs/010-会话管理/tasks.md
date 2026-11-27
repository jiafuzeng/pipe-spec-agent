# Tasks: 会话管理

**Input**: Design documents from `.specify/specs/010-会话管理/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/session-history.md、quickstart.md

**Tests**: quickstart 要求先写会失败的列表测试。页面行为在浏览器核对。

**Organization**: 按用户故事分组。历史列表和打开一段聊天沿用现有会话接口，不新增记忆类型。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可与不同文件的任务并行
- **[Story]**: 对应用户故事 US1、US2、US3

## Phase 1: Setup

**Purpose**: 确认沿用现有工作台，不新开会话库

- [X] T001 确认历史会话仍读 `app/agent/store.py` 的现有会话表，页面仍在 `frontend/src/Chat.jsx`，主导航仍在 `frontend/src/main.jsx`

---

## Phase 2: Foundational

**Purpose**: 列表按最近提问排序，打开一段时返回全部提问。阻塞后续故事。

- [X] T002 在 `tests/test_sessions.py` 先写失败测试：较晚活动的会话排在前面，`历史会话条目.last_message` 与 `历史会话条目.last_activity_at` 对应该段最近一次提问（见 data-model.md），没有提问的会话不出现，列表不含其他会话的 `messages`
- [X] T003 在 `tests/test_sessions.py` 先写失败测试：`GET /api/v1/sessions/{sid}` 按发生顺序返回该段全部提问，不截断为 30 条（见 data-model.md `聊天记录.顺序`）
- [X] T004 在 `app/agent/store.py` 的 `list_sessions` 实现 data-model.md 的 `历史会话条目.last_message`、`历史会话条目.last_activity_at`，按 `历史会话条目.last_activity_at` 从新到旧，并排除没有提问的 `会话.id`
- [X] T005 在 `app/agent/store.py` 的 `session` 按 `聊天记录.顺序` 返回该 `会话.id` 的全部用户提问

**Checkpoint**: `.venv/bin/python -m unittest tests.test_sessions -v` 通过

---

## Phase 3: User Story 1 - 从左侧打开历史会话并继续聊 (Priority: P1)

**Goal**: 问答页左侧列出历史会话，点开后只看到这一段，并能继续发送。

**Independent Test**: 两段各有提问时，左侧能区分；点开一段只有该段内容；再发一条后只留在这一段。

### Implementation for User Story 1

- [X] T006 [US1] 在 `frontend/src/Chat.jsx` 与 `frontend/src/style.css` 把历史会话放成问答页左列，每条显示 `历史会话条目.last_message` 的一行开头和 `历史会话条目.last_activity_at`，最近活动在上，并可滚动
- [X] T007 [US1] 在 `frontend/src/Chat.jsx` 点开 `历史会话条目.session_id` 时只恢复该段提问和对应运行事件；等待回答时左侧其他会话和「新会话」不可点
- [X] T008 [US1] 在 `frontend/src/main.jsx` 保持导入文档和评测入口可达

**Checkpoint**: 左侧能打开一段并只看到该段问答

---

## Phase 4: User Story 2 - 新开一段而不丢掉旧会话 (Priority: P2)

**Goal**: 新段从空白开始，旧段仍留在左侧。

**Independent Test**: 新开一段并提问后，点回旧段仍是旧内容。

### Implementation for User Story 2

- [X] T009 [US2] 在 `frontend/src/Chat.jsx` 的「新会话」清空主区域且不写入 `上次打开.session_id` 对应的旧聊天；第一条提问前该段不出现在左侧。没有历史会话时显示「还没有历史会话」

**Checkpoint**: 新段与旧段可以来回点，内容不混

---

## Phase 5: User Story 3 - 重新打开工作台后仍能接着聊 (Priority: P3)

**Goal**: 重新打开问答页进入上次那段；那段不在时停留空白新对话。

**Independent Test**: 刷新后仍是刷新前的会话。把上次打开改成不存在的标识后，主区域没有另一段的句子。

### Implementation for User Story 3

- [X] T010 [US3] 在 `frontend/src/Chat.jsx` 用浏览器本地存储只保存 data-model.md 的 `上次打开.session_id`。重新打开时该标识仍在列表中才打开；不在列表中或打开失败时停留空白新对话，并说明暂时打不开，不改显示另一段的内容

**Checkpoint**: 刷新后继续上次那段

---

## Phase 6: Polish

**Purpose**: 按 quickstart 收口

- [X] T011 运行 `.venv/bin/python -m unittest tests.test_sessions tests.test_application tests.test_dialogue -v`，确认会话列表变更没有破坏既有问答测试

---

## Dependencies & Execution Order

- T002、T003 先于 T004、T005
- T004、T005 完成后再做 T006 及之后的页面任务
- US2、US3 依赖 US1 的左列和打开逻辑

## Parallel Example: User Story 1

```text
T006 frontend/src/Chat.jsx 与 frontend/src/style.css
T008 frontend/src/main.jsx 只核对，不改主导航
```

## Implementation Strategy

先完成列表排序和全部提问读取（US1 的服务端），再做左列。新开一段和重新打开都建立在同一套打开逻辑上。MVP 是左侧能点开一段并只看到该段问答。
