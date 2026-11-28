import unittest

from app.agent.answers import (
    REFUSAL,
    classify_turn,
    format_answer,
    grounded_summary,
    normalize_citations,
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
    def test_chitchat_and_qa(self):
        self.assertEqual(classify_turn("你好"), "chitchat")
        self.assertEqual(classify_turn("第1.0.1条写了什么？"), "qa")
        self.assertEqual(classify_turn("计算 RI"), "qa")

    def test_compare_by_methods(self):
        self.assertEqual(classify_turn("CCTV 与 QV 的适用条件有何差异？"), "compare")


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
