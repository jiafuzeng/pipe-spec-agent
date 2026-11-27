import unittest

from app.agent.answers import render_compare, render_explain, render_plan


CCTV = {
    "evidence_id": "a",
    "clause_no": "2.1.1",
    "quote": "CCTV 检测即电视检测，使用闭路电视系统。",
}
QV = {
    "evidence_id": "b",
    "clause_no": "2.1.2",
    "quote": "QV 检测即潜望镜检测。",
}
SONAR = {
    "evidence_id": "c",
    "clause_no": "2.1.3",
    "quote": "声纳检测利用声波获取管内轮廓。",
}
LEVEL = {
    "evidence_id": "w",
    "clause_no": "4.1.2",
    "quote": "电视检测时，管内水位不宜大于管径的20%。",
}
DIVER = {
    "evidence_id": "d",
    "clause_no": "7.1.2",
    "quote": "潜水检测的管径不小于1200mm。",
}
HALF = {
    "evidence_id": "h",
    "clause_no": "6.1.2",
    "quote": "QV 检测时水位不宜大于管径的1/2。",
}
BAN = {
    "evidence_id": "s",
    "clause_no": "5.4.5",
    "quote": "声纳检测不得单独作为结构性缺陷的判定依据。",
}
ORDER = {
    "evidence_id": "m",
    "clause_no": "9.0.1",
    "quote": "检查井检测应安排在管道检测之前。",
}

COMPARE = "CCTV、QV、声纳三种检测方式的官方术语定义分别是什么？各自的适用条件有何差异？"
PLAN = (
    "某 DN800 混凝土污水管，埋深约 4.5 m，管内水位约 60%，积泥较厚，"
    "位于城市次干道，现场不具备停水降水条件。请给出检测方案、实施顺序、安全措施和选择依据。"
)
WHY = "声纳检测为何不能单独作为结构性缺陷的判定依据？检查井检测应安排在管道检测之前还是之后？"


class CompareTests(unittest.TestCase):
    def test_splits_named_methods_and_concludes(self):
        text = render_compare(COMPARE, [CCTV, QV, SONAR])
        self.assertIn("### CCTV", text)
        self.assertIn("### QV", text)
        self.assertIn("### 声纳", text)
        self.assertIn("〔2.1.1〕", text)
        self.assertIn("〔2.1.2〕", text)
        self.assertIn("〔2.1.3〕", text)
        self.assertIn("选择结论", text)
        self.assertNotIn("20%", text)

    def test_unnamed_hit_is_not_invented(self):
        query = "从四个维度列表对比 CCTV、QV、声纳、人工下井、潜水五种检测方式，并给出选择结论。"
        text = render_compare(query, [CCTV])
        self.assertIn("### 人员进入", text)
        self.assertIn("未检索到", text)
        self.assertIn("选择结论", text)
        self.assertNotIn("宜采用潜水", text)

    def test_empty_evidence_refuses(self):
        self.assertIsNone(render_compare(COMPARE, []))


class PlanTests(unittest.TestCase):
    def test_lists_missing_and_quote_conflicts(self):
        text = render_plan(PLAN, [LEVEL, DIVER, HALF])
        self.assertIn("已知条件", text)
        self.assertIn("DN800", text)
        self.assertIn("60%", text)
        for item in ("埋没探头", "流速", "管段长度", "竣工资料"):
            self.assertIn(item, text)
        self.assertIn("〔4.1.2〕", text)
        self.assertIn("〔7.1.2〕", text)
        self.assertIn("〔6.1.2〕", text)
        self.assertIn("因此不能采用", text)
        self.assertIn("不给出最终", text)
        self.assertNotIn("推荐采用声纳", text)

    def test_equal_limit_is_not_a_violation(self):
        query = "DN1200，管内水位约 20%。请给出检测方案。"
        text = render_plan(query, [LEVEL, DIVER])
        self.assertNotIn("因此不能采用", text)

    def test_empty_evidence_refuses(self):
        self.assertIsNone(render_plan(PLAN, []))


class ExplainTests(unittest.TestCase):
    def test_states_only_what_the_quote_says(self):
        text = render_explain(WHY, [BAN, ORDER])
        self.assertIn("〔5.4.5〕", text)
        self.assertIn("不能单独", text)
        self.assertIn("不补充规程外理由", text)
        self.assertIn("〔9.0.1〕", text)
        self.assertIn("之前", text)

    def test_does_not_invent_order(self):
        text = render_explain(WHY, [BAN])
        self.assertNotIn("安排在管道检测之前", text)

    def test_empty_evidence_refuses(self):
        self.assertIsNone(render_explain(WHY, []))


class GroundingRegressionTests(unittest.TestCase):
    def test_conclusion_identifies_method_specific_selection_condition(self):
        text = render_compare("比较电视检测和潜望镜检测", [LEVEL, QV])
        conclusion = text.split("选择结论：")[1]
        self.assertIn("CCTV", conclusion)
        self.assertIn("4.1.2", conclusion)
        self.assertIn("20%", conclusion)

    def test_unknown_conditions_still_prompt(self):
        text = render_plan("检测方案：流速未知，管段长度待测，积泥是否埋没探头不明，有无竣工资料待确认。", [LEVEL])
        missing = text.split("缺失且")[1].split("已给条件")[0]
        for name in ("流速", "管段长度", "埋没探头", "竣工资料", "管径", "水位"):
            self.assertIn(name, missing)

    def test_confirmed_conditions_are_shown(self):
        text = render_plan(PLAN + "流速0.4m/s，管段长度80m，积泥未埋没探头，无竣工资料。", [LEVEL])
        known, missing = text.split("缺失且")
        for fact in ("0.4m/s", "80m", "未埋没探头", "无竣工资料"):
            self.assertIn(fact, known)
        self.assertIn("- 无", missing.split("已给条件")[0])

    def test_limit_belongs_to_its_own_method_and_quantity(self):
        evidence = [dict(LEVEL, quote="电视检测采用摄像机。潜水检测的管径不小于1200mm。"),
                    dict(HALF, quote="QV检测时积泥厚度不宜大于管径的1/2。")]
        text = render_plan(PLAN, evidence)
        self.assertIn("因此不能采用潜水", text)
        self.assertNotIn("因此不能采用CCTV", text)
        self.assertNotIn("因此不能采用QV", text)

    def test_no_inferred_prohibition_or_inverted_order(self):
        items = [dict(BAN, quote="声纳检测不得损伤设备，可用于结构性缺陷调查。"),
                 dict(ORDER, quote="管道检测在检查井检测之前。")]
        text = render_explain(WHY, items)
        self.assertNotIn("声纳不能单独", text)
        self.assertNotIn("检查井检测安排在管道检测之前", text)

    def test_real_clause_wording_and_workbench_questions(self):
        from app.agent.answers import classify_turn
        query = "DN800 污水管，水位 60%，次干道且不能停水降水，应如何检测？"
        self.assertEqual(classify_turn(query), "plan")
        self.assertEqual(classify_turn("声纳能否单独判定结构性缺陷？何时检查检查井？"), "explain")
        quote = "电视检测不应带水作业。当现场条件无法满足时，应采取降低水位措施，确保管道内水位不大于管道直径的20%。"
        self.assertIn("因此不能采用CCTV", render_plan(query, [dict(LEVEL, quote=quote)]))
