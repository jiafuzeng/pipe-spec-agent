import unittest
from decimal import Decimal
from rag.calculation import evaluate, missing_fields


class CalculationTests(unittest.TestCase):
    def test_cal03_grade_boundary(self):
        rule = dict(
            fields=[dict(name="X", minimum=0, maximum=10)],
            formula="I = 0.5 X",
            coefficients={"X": "0.5"},
            bands=[
                {"upper": "1", "grade": "A", "advice": "a"},
                {"upper": None, "grade": "B", "advice": "b"},
            ],
            evidence=["fixture"],
        )
        out = evaluate(rule, {"X": 2})
        self.assertEqual(Decimal(out["value"]), Decimal(1))
        self.assertEqual(out["grade"], "A")
        self.assertEqual(evaluate(rule, {"X": "2.01"})["grade"], "B")
        for x in ["NaN", "Infinity", 11, True]:
            with self.assertRaises(ValueError):
                evaluate(rule, {"X": x})

    def test_ag02_schema_drives_clarification(self):
        fields = [
            dict(name="K", description="用途", evidence_refs=["fixture"]),
            dict(name="T"),
        ]
        self.assertEqual(missing_fields(fields, {"T": 0}), fields[:1])

    def test_cal08_real_drafts_never_publish(self):
        from rag.calculation import rulebook
        from rag.draft_rules import ROOT, candidate_rules

        drafts = dict(candidate_rules(ROOT))
        self.assertEqual(len(drafts["RI"]["bands"]), 4)
        row = next(
            r
            for r in drafts["defect_score"]["rows"]
            if r["defect"] == "错口" and r["grade"] == 3
        )
        self.assertEqual(row["score"], "5")
        for kind in drafts:
            self.assertIsNone(rulebook(kind))
