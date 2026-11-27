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

    def test_cal08_no_published_rules_without_fixture(self):
        import os
        from rag.calculation import rulebook

        os.environ.pop("RULE_FIXTURE", None)
        for kind in ("RI", "MI", "defect_score"):
            self.assertIsNone(rulebook(kind))

    def test_fixture_ri_loads_only_with_flag(self):
        import os
        from rag.calculation import rulebook

        os.environ.pop("RULE_FIXTURE", None)
        self.assertIsNone(rulebook("RI"))
        os.environ["RULE_FIXTURE"] = "1"
        try:
            rule = rulebook("RI")
            self.assertIsNotNone(rule)
            self.assertTrue(rule.get("fixture_only"))
            self.assertEqual(rule["version"], "CJJ181-2012-fixture-ri-7.1")
        finally:
            os.environ.pop("RULE_FIXTURE", None)
