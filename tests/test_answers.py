import unittest

from app.agent.answers import (
    REFUSAL,
    answer_evidence,
    classify_turn,
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


class SummaryTests(unittest.TestCase):
    def test_grounded_summary(self):
        text = grounded_summary(PURPOSE)
        self.assertIn("制定本规程〔1.0.1〕。", text)
        self.assertIn("检测与评估〔1.0.2〕。", text)

    def test_normalize_citations(self):
        self.assertEqual(normalize_citations("见[1.0.1]"), "见〔1.0.1〕")

    def test_empty_evidence(self):
        self.assertIsNone(grounded_summary([]))
        self.assertIn("无相关规定", REFUSAL)

    def test_compare_filters_methods(self):
        rows = answer_evidence(
            "compare",
            "CCTV 与 QV 差异",
            PURPOSE
            + [
                {
                    "evidence_id": "c",
                    "clause_no": "2.1.1",
                    "quote": "CCTV 检测即电视检测。",
                }
            ],
        )
        self.assertTrue(any("CCTV" in row["quote"] for row in rows))
