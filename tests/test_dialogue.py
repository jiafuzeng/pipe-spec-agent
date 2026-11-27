import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.dialogue import REFUSAL, router


class TurnTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"AGENT_MODEL_ENABLED":"0"})
        env.start()
        self.addCleanup(env.stop)
        app = FastAPI()
        app.include_router(router)
        self.api = TestClient(app)
        sid = self.api.post("/api/v1/sessions").json()["session_id"]
        self.url = f"/api/v1/sessions/{sid}/turns"

    def test_compare_skips_calculation_tools(self):
        evidence = [
            {
                "evidence_id": "a",
                "clause_no": "2.1.1",
                "quote": "CCTV 检测即电视检测。",
            },
            {
                "evidence_id": "b",
                "clause_no": "2.1.2",
                "quote": "QV 检测即潜望镜检测。",
            },
        ]
        with (
            patch("app.agent.workflow.search_clauses", return_value={"evidence": evidence}),
            patch("app.agent.workflow.select_evidence", AsyncMock(return_value=evidence)),
            patch("app.agent.workflow.call_tool", AsyncMock()) as tool,
        ):
            text = self.api.post(
                self.url,
                json={
                    "message": "CCTV 与 QV 的适用条件有何差异？",
                },
            ).text
        tool.assert_not_called()
        self.assertIn("event: plan_step", text)
        self.assertIn("选择结论", text)
        self.assertIn("2.1.1", text)

    def test_plan_without_evidence_refuses(self):
        with (
            patch("app.agent.workflow.search_clauses", return_value={"evidence": []}),
            patch("app.agent.workflow.call_tool", AsyncMock()) as tool,
        ):
            text = self.api.post(
                self.url,
                json={"message": "请给出检测方案。"},
            ).text
        tool.assert_not_called()
        self.assertIn(REFUSAL, text)

    def test_kn04_no_evidence(self):
        with patch("app.agent.workflow.search_clauses", return_value={"evidence": []}):
            self.assertIn(
                REFUSAL, self.api.post(self.url, json={"message": "库外问题"}).text
            )

    def test_search_does_not_call_mcp(self):
        with (
            patch("app.agent.workflow.search_clauses", return_value={"evidence": []}) as search,
            patch("app.agent.workflow.call_tool", AsyncMock()) as tool,
        ):
            self.api.post(self.url, json={"message": "第1.0.1条写了什么？"})
            search.assert_called_once()
            tool.assert_not_called()

    def test_cal08_unreleased(self):
        with patch(
            "app.agent.workflow.call_tool",
            AsyncMock(return_value=dict(status="pending_review", reason="待核验")),
        ) as tool:
            response = self.api.post(self.url, json={"message": "计算养护指数"})
            tool.assert_awaited_once_with(
                "get_calculation_schema", {"calculation_type": "MI"}
            )
            self.assertIn("待核验", response.text)

    def test_ag06_mcp_failure_on_calculation(self):
        with patch("app.agent.workflow.call_tool", AsyncMock(side_effect=RuntimeError)):
            text = self.api.post(self.url, json={"message": "计算修复指数 RI"}).text
            self.assertIn("event: error", text)
            self.assertIn("TOOL_UNAVAILABLE", text)
            self.assertNotIn("event: answer", text)

    def test_cal04_curve_requires_confirmed_fixed_parameters(self):
        fields = [{"name": v} for v in ("F", "K", "E", "T")]
        calls = []

        async def dispatch(name, args):
            calls.append((name, args))
            if name == "get_calculation_schema":
                return dict(status="approved", fields=fields, rule_version="fixture")
            if name == "calculate_index":
                return {"result_id": "test-" + str(args["parameters"]["K"])}
            return {
                "resource_id": "chart-fixture",
                "png_base64": "fixture",
                "csv": "fixture",
                "points": [],
            }

        with patch("app.agent.workflow.call_tool", dispatch):
            first = self.api.post(
                self.url, json={"message": "画 RI 曲线 K=0、3、6、10"}
            ).text
            self.assertIn("clarification_required", first)
            self.assertEqual(len(calls), 1)
            second = self.api.post(self.url, json={"message": "F=5 E=6 T=8"}).text
            self.assertIn("event: chart", second)
            self.assertEqual(
                [x[1]["parameters"]["K"] for x in calls if x[0] == "calculate_index"],
                ["0", "3", "6", "10"],
            )
