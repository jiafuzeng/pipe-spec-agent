<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0
- Modified principles:
  I. 唯一知识源 → I. 唯一知识源（正式问答仅使用已审核正文）
  IV. 双交付物边界 → IV. 双交付物边界（写明 MCP 独立部署）
- Added sections: none
- Removed sections: none
- Expanded sections: 开发流程（计划、任务、回归、验收记录）；
  Governance（保留批准日，修订须写原因和影响范围）
- Follow-up TODOs: none
- Reason: 对照 specs/01-governance/constitution.md 与五条长期原则，
  把尚未可检查的约束写入章程。
- Impact: 未审核文本不得进入正式问答；功能完成必须有回归和验收记录；
  章程修订必须说明原因和影响范围。拒答语句、计算工具归属和批准日不变。
-->

# Pipe Spec Agent Constitution

## Core Principles

### I. 唯一知识源（NON-NEGOTIABLE）

知识库只收录附件规程 PDF《CJJ 181—2012》正文。实现、提示词、测试夹具
和现场答辩都不得引入教材、博客、条文说明或其他标准。正式问答 MUST 只使用
已审核的该正文。未审核内容 MUST NOT 作为正式问答证据。

检索未命中可用条款时，回答 MUST 固定为：

> 依据 CJJ 181—2012 原文无相关规定，不作推测性补充。

每条规程结论 MUST 标注条款号或表号。系统 MUST NOT 自造条款号，MUST NOT
把模型记忆写成规程原文。正文没有写明的等同关系（例如把「流砂」当成
「粉砂层」）MUST NOT 自动建立。

### II. 计算不心算（NON-NEGOTIABLE）

加减乘除、等级比较和参数查表 MUST 由 `pipe-assessment-mcp` 的确定性工具执行。
Agent 只负责识别意图、检查槽位、填写工具参数、引用工具返回的中间量和组织
工程结论。回答中的数值 MUST 能在同一次工具返回中核对；对不上则丢弃该数值，
并说明工具结果未能核对，MUST NOT 改由模型心算补上。参数不足时 MUST 先追问，
列出缺失项、该项的作用、对应条款或表号。补齐前 MUST NOT 调用计算器，
MUST NOT 输出指数或等级。

### III. 测试先行（NON-NEGOTIABLE）

先改可观察行为的规格，再写会失败的测试，再做最小实现。冲突或缺原文依据时
标「未决」，MUST NOT 自行推定业务规则。未核验的公式、分档、等级或强制性
要求 MUST NOT 标为已批准。确定性规则使用固定输入测试；编排测试使用可控
替身，MUST NOT 依赖真实模型的自由生成结果。

### IV. 双交付物边界

`pipe-spec-agent` 负责会话、导入审核、规程检索和 Agent 编排。`search_clauses`
只在该进程内执行。独立部署的 `pipe-assessment-mcp` 负责查表、计算和绘图，
拥有自己的存储与规则包，MUST NOT 提供条文检索。MCP 离线 MUST NOT 阻止
导入和条文问答。

### V. 规则发布门禁

正式计算 MUST 只加载经过双人审核且通过 `validate_rules` 的规则包。评测夹具
仅用于测试，MUST NOT 进入 `rules/published/`。未发布规则时，计算请求 MUST
返回核验状态，MUST NOT 输出正式 RI/MI。

## 会话与表达

同一会话里用户已经确认的槽位保持有效。后续回合直接使用，不重复追问。
用户明确修改某项时只更新该项。目标管段改变、取值冲突或单位不明时，
MUST 先澄清。

对比类问题 MUST 用分点或表格，并给出选择结论。需要曲线的问题 MUST 展示
工具生成的图；文字趋势不能代替图。方案类问题 MUST 按规程中的「应 / 不得 /
不宜」核对现场条件。条件不满足时 MUST 写明因此不能采用该方法，并引用条款。

现场运行时规划步骤和 MCP 调用记录 MUST 保持可见。

## 开发流程

功能变更 MUST 先写规格和验收场景，再制定计划、拆分任务。实现前 MUST 先写
失败测试。完成后 MUST 运行回归，并记录验收结果。

行为以 `specs/` 的阶段规格为基线：治理、需求、设计、开发、测试、交付。
Spec Kit 功能目录只切片实施其中尚未落地的行为。阶段规格与功能规格冲突时，
以阶段规格为准，并先改规格再改代码。

## Governance

本章程约束实现、提示词、测试夹具和答辩。原始批准日期 MUST 保留为 2026-11-26，
修订 MUST NOT 改写该日期。

修正章程时递增语义化版本：不兼容的原则删除或重定义为 MAJOR，新增原则或
实质性扩充为 MINOR，措辞澄清为 PATCH。每次修订 MUST 写明日期、变更原因和
影响范围，并同步检查阶段规格里的对应句子。评审 MUST 核对知识边界、
计算是否心算、未发布规则是否被当成正式结果。

**Version**: 1.1.0 | **Ratified**: 2026-11-26 | **Last Amended**: 2026-11-27
