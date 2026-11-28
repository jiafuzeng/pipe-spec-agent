import unittest

from app.agent.answers import (
    REFUSAL,
    TASK_CASES,
    classify_turn,
    format_answer,
    grounded_summary,
    normalize_citations,
    skip_intent_llm,
)

PURPOSE = [
    {
        "evidence_id": "p1",
        "clause_no": "1.0.1",
        "quote": "1.0.1 为加强城镇排水管道检测管理，规范检测技术，统一评估标准，制定本规程。",
    },
    {
        "evidence_id": "p2",
        "clause_no": "1.0.2",
        "quote": "1.0.2 本规程适用于对既有城镇排水管道及其附属构筑物进行的检测与评估。",
    },
]


class ClassifyTests(unittest.TestCase):
    def test_chitchat_and_retrieve(self):
        self.assertEqual(classify_turn("你好"), "chitchat")
        self.assertEqual(classify_turn("第1.0.1条写了什么？"), "retrieve")
        self.assertEqual(classify_turn("检查井为何要在声纳之前"), "retrieve")
        self.assertEqual(
            classify_turn("CJJ 181—2012 的编制目的与适用范围是什么？"),
            "retrieve",
        )
        self.assertEqual(
            classify_turn(
                "管道结构性缺陷与功能性缺陷的普查周期分别是多久？哪些情形下应缩短检测周期？"
            ),
            "retrieve",
        )
        self.assertEqual(classify_turn("结构性缺陷和功能性缺陷有何区别"), "retrieve")
        self.assertEqual(classify_turn("检测方案应包括哪些内容？"), "retrieve")
        self.assertEqual(classify_turn("修复指数公式是什么？RI 怎么分级？"), "retrieve")
        self.assertEqual(classify_turn("直向摄影和侧向摄影有何区别"), "retrieve")
        self.assertEqual(
            classify_turn("声纳检测为何不能单独作为结构性缺陷判定依据？"),
            "compare",
        )
        self.assertEqual(classify_turn("CCTV 与 QV 的适用条件有何差异？"), "retrieve")
        self.assertEqual(
            classify_turn("传统方法与电视检测分别适用于什么检查？"),
            "retrieve",
        )
        self.assertEqual(
            classify_turn(
                "CCTV、QV、声纳三种检测方式的官方术语定义分别是什么？各自的适用条件有何差异？"
            ),
            "retrieve",
        )
        self.assertTrue(
            skip_intent_llm(
                "CCTV、QV、声纳三种检测方式的官方术语定义分别是什么？各自的适用条件有何差异？",
                "retrieve",
            )
        )

    def test_compare_by_methods(self):
        self.assertEqual(classify_turn("两种检测方案怎么对比"), "compare")
        self.assertEqual(classify_turn("请给出检测方案。"), "compare")
        self.assertEqual(
            classify_turn("列表对比五种检测方式并给出选择结论"),
            "compare",
        )
        self.assertEqual(
            classify_turn(
                "某 DN800 混凝土污水管，管内水位约 60%，请规划检测方案并推荐检测方式"
            ),
            "compare",
        )

    def test_compute_by_calc_or_chart(self):
        self.assertEqual(classify_turn("计算 RI"), "compute")
        self.assertEqual(classify_turn("已知 F=6、K=0、E=3、T=0，计算 RI"), "compute")
        self.assertEqual(classify_turn("把缺陷统计画成图"), "compute")
        self.assertEqual(classify_turn("评估标准是什么"), "retrieve")
        self.assertEqual(classify_turn("养护指数怎么分级"), "retrieve")

    def test_task_book_nine_questions(self):
        for query, expected in TASK_CASES:
            with self.subTest(query=query[:24], expected=expected):
                hint = classify_turn(query)
                self.assertEqual(hint, expected)
                self.assertTrue(skip_intent_llm(query, hint))


class SummaryTests(unittest.TestCase):
    def test_format_answer(self):
        text = format_answer(
            "按总则，编制目的和适用范围可以分开看。",
            [
                {"title": "编制目的", "body": "主要是把检测管理、技术和评估标准统一起来。"},
                {"title": "适用范围", "body": "针对已建成的城镇排水管道和附属构筑物。"},
            ],
        )
        self.assertIn("### 编制目的\n", text)
        self.assertIn("### 适用范围\n", text)
        self.assertTrue(text.startswith("按总则"))

    def test_grounded_summary(self):
        text = grounded_summary(PURPOSE)
        self.assertIn("### 1.0.1", text)
        self.assertIn("制定本规程", text)
        self.assertNotIn("〔1.0.1〕", text)
        self.assertNotIn("原文：", text)

    def test_normalize_citations(self):
        self.assertEqual(normalize_citations("见[1.0.1]结论"), "见结论")
        self.assertEqual(normalize_citations("要点 〔1.0.2〕"), "要点")

    def test_empty_evidence(self):
        self.assertIsNone(grounded_summary([]))
        self.assertIn("无相关规定", REFUSAL)
