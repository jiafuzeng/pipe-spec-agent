import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipe_assessment_mcp.validate_rules import validate_package
from rag.calculation import rulebook
from rag.source import PDF_SHA


class ValidateRulesTests(unittest.TestCase):
    def test_rejects_single_reviewer_and_fixture(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "RI.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "approved",
                        "fixture_only": True,
                        "version": "x",
                        "source_hash": PDF_SHA,
                        "reviewers": ["only-one"],
                        "evidence": ["8.3.4"],
                        "fields": [
                            {"name": "F", "minimum": 0, "maximum": 10},
                            {"name": "K", "minimum": 0, "maximum": 10},
                            {"name": "E", "minimum": 0, "maximum": 10},
                            {"name": "T", "minimum": 0, "maximum": 10},
                        ],
                        "formula": "RI = F",
                        "coefficients": {"F": "1", "K": "0", "E": "0", "T": "0"},
                        "bands": [{"grade": "Ⅰ", "upper": None, "advice": "a"}],
                        "reference_cases": [
                            {
                                "parameters": {"F": "1", "K": "0", "E": "0", "T": "0"},
                                "value": "1",
                                "grade": "Ⅰ",
                            },
                            {
                                "parameters": {"F": "2", "K": "0", "E": "0", "T": "0"},
                                "value": "2",
                                "grade": "Ⅰ",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_package(path)
            self.assertTrue(any("fixture_only" in e for e in errors))
            self.assertTrue(any("reviewers" in e for e in errors))

    def test_rulebook_ignores_worksheets(self):
        os.environ.pop("RULE_FIXTURE", None)
        self.assertIsNone(rulebook("RI"))


if __name__ == "__main__":
    unittest.main()
