import unittest
from decimal import Decimal


class DefectInputTests(unittest.TestCase):
    def test_pair_spacing_and_diameter_boundaries(self):
        from pipe_assessment_mcp.defects import derive_pair

        policy = {
            "overlap_m": "1",
            "near_m": "1.5",
            "near_weight": "1.1",
            "score_cap": "10",
        }
        for gap, mean, peak in [
            ("0.9", "10", "10"),
            ("1.2", "5.5", "5"),
            ("1.5", "5.5", "5"),
            ("1.6", "5", "5"),
        ]:
            result = derive_pair([5, 5], gap, policy)
            self.assertEqual(Decimal(result["S"]), Decimal(mean))
            self.assertEqual(Decimal(result["Smax"]), Decimal(peak))
            self.assertEqual(Decimal(result["F"]), max(Decimal(mean), Decimal(peak)))

    def test_fixture_without_reviewed_domain_cannot_derive(self):
        import os
        from unittest.mock import patch
        from pipe_assessment_mcp.server import calculate_index

        with patch.dict(os.environ, {"RULE_FIXTURE": "1"}):
            result = calculate_index(
                "RI",
                "CJJ181-2012-fixture-ri-7.1",
                {"defects": [{}, {}], "D": 1200},
                "invalid",
            )
        self.assertEqual(result.get("error"), "RULE_NOT_PUBLISHED")
        self.assertNotIn("value", result)

    def test_raw_inputs_use_score_table_and_preserve_trace(self):
        from pipe_assessment_mcp.defects import InputError, resolve_inputs
        from rag.draft_rules import candidate_rules, ROOT

        draft = dict(candidate_rules(ROOT))["RI"]
        query = {
            "defects": [{"defect": "错口", "grade": 3, "score": "5"}] * 2,
            "gap_m": "1.2",
            "D": "1200",
            "soil": "粉砂层",
            "K": "6",
        }

        def lookup(name, grade, version):
            self.assertEqual((name, grade, version), ("错口", 3, draft["version"]))
            return {"row": {"score": "5", "evidence": "表8.2.3"}}

        values, trace = resolve_inputs(draft, query, lookup)
        self.assertEqual(Decimal(values["F"]), Decimal("5.5"))
        self.assertEqual(values["E"], "6")
        self.assertEqual(values["T"], "10")
        self.assertEqual(trace[2]["group"], "n2")
        with self.assertRaises(InputError) as err:
            resolve_inputs(draft, query | {"soil": "流砂"}, lookup)
        self.assertEqual(err.exception.payload["error"], "AMBIGUOUS_MAPPING")
        with self.assertRaises(InputError):
            resolve_inputs(
                draft,
                query | {"defects": [{"defect": "错口", "grade": 3, "score": "4"}] * 2},
                lookup,
            )

    @unittest.skip("agent calculation flow removed")
    def test_site_facts_are_collected_before_unknown_soil(self):
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from app.server.application import create_app
        from app.server.routes.sessions import Store
        from agentEval.run import parse_sse

        calls = []

        async def tool(name, args):
            calls.append(name)
            if name == "get_calculation_schema":
                return {
                    "status": "approved",
                    "rule_version": "contract-test",
                    "alternate_inputs": {
                        "grades": {"重度": 3},
                        "soil_columns": ["粉砂层"],
                    },
                    "fields": [{"name": k} for k in ("F", "K", "E", "T")],
                }
            if name == "lookup_defect_score":
                return {"row": {"score": "5"}}
            raise AssertionError(name)

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"AGENT_MODEL_ENABLED": "0"}),
            TestClient(create_app(Store(Path(tmp) / "agent.sqlite"), tool)) as api,
        ):
            sid = api.post("/api/v1/sessions").json()["session_id"]
            q = "DN1200，主干道（K=6），土质为流砂；管段存在 2 处重度错口（单处分值 5），缺陷纵向间距 1.2 m。计算 RI。"
            events = parse_sse(
                api.post(f"/api/v1/sessions/{sid}/turns", json={"message": q}).text
            )
            self.assertEqual(calls, ["get_calculation_schema", "lookup_defect_score"])
            self.assertEqual(events[-1]["type"], "clarification_required")
            self.assertEqual([f["name"] for f in events[-1]["fields"]], ["T"])
            self.assertIn("粉砂层", events[-1]["fields"][0]["description"])
