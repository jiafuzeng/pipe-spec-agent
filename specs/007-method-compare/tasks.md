# Tasks: 检测方法对比与检测方案

**Input**: Design documents from `/specs/007-method-compare/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/turn.md

**Tests**: 章程要求测试先行。本功能先写失败测试，再写最小实现。

**Organization**: 按用户故事分段，使比较、方案、解释可以分开验收。

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: 确认现有工程可挂上纯函数，不新建项目

- [X] T001 确认 `rag/dialogue.py` 的非计算回合仍是检索后拼原文，并在 `specs/007-method-compare/plan.md` 记录挂载点

## Phase 2: Foundational

**Purpose**: 三类意图共用的证据过滤。完成前不改对话分支

- [X] T002 在 `rag/answers.py` 定义 `MethodNote` 所用方法别名（CCTV、QV、声纳、人员进入、潜水），人员进入包含「人工下井」

## Phase 3: User Story 1 - 按条款对比检测方法 (Priority: P1)

**Goal**: 比较题按方法分段并给出选择结论

**Independent Test**: `tests/test_answers.py` 中比较用例；对话测试确认不调用计算工具

- [X] T003 [P] [US1] 在 `tests/test_answers.py` 写比较分段、未命中方法、空证据拒答的失败测试
- [X] T004 [US1] 在 `rag/answers.py` 实现 `render_compare`，只引用 `EvidenceQuote.clause_no` 与 `EvidenceQuote.quote`
- [X] T005 [US1] 在 `rag/dialogue.py` 把比较意图接到检索回合，并在 `tests/test_dialogue.py` 断言无计算工具调用

## Phase 4: User Story 2 - 条件不足时先追问检测方案 (Priority: P2)

**Goal**: 方案题列出 `PlanCheck.known`、`PlanCheck.missing`，冲突时写明因此不能采用

**Independent Test**: 固定证据含「不宜大于管径的20%」和「管径不小于1200mm」时，DN800、水位 60% 被否决；无证据则拒答

- [X] T006 [P] [US2] 在 `tests/test_answers.py` 写 `PlanCheck.missing` 四项、`PlanCheck.violations` 和空证据的失败测试
- [X] T007 [US2] 在 `rag/answers.py` 实现 `render_plan`：界限只从 `EvidenceQuote.quote` 解析；`PlanCheck.may_recommend` 为假时不给最终推荐
- [X] T008 [US2] 在 `rag/dialogue.py` 接通方案意图

## Phase 5: User Story 3 - 解释禁止性结论与检查顺序 (Priority: P3)

**Goal**: `ExplainFinding` 只在原文有对应表述时产生肯定句

**Independent Test**: 原文含「不能单独」和「之前」才出现这两句；否则不出现

- [X] T009 [P] [US3] 在 `tests/test_answers.py` 写 `ExplainFinding.kind` 为 prohibition 与 order 的失败测试
- [X] T010 [US3] 在 `rag/answers.py` 实现 `render_explain` 并在 `rag/dialogue.py` 接通

## Phase 6: Polish

- [X] T011 运行 `tests/test_answers.py` 与 `tests/test_dialogue.py`，并在 `specs/README.md` 挂上本功能目录

## Dependencies

- US1 → US2 → US3 顺序实施（同一 `rag/answers.py` 与 `rag/dialogue.py`）
- T003 先于 T004；T006 先于 T007；T009 先于 T010

## Parallel Example

- T003 与 T006 可同时起草，但落地时按故事顺序提交到同一测试文件

## Implementation Strategy

先交付 US1（比较分段）。US2、US3 复用同一检索回合，不改计算路径。
