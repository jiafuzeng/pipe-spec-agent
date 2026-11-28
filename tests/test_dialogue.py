import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from rag.dialogue import REFUSAL


class TurnTests(unittest.TestCase):
    def setUp(self):
        from app.server.application import create_app

        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = patch.dict(
            "os.environ",
            {
                "AGENT_MODEL_ENABLED": "0",
                "LANGGRAPH_DB": str(Path(self._tmp.name) / "langgraph.sqlite"),
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self._client_cm = TestClient(create_app())
        self.api = self._client_cm.__enter__()
        self.addCleanup(self._client_cm.__exit__, None, None, None)
        sid = self.api.post("/api/v1/sessions").json()["session_id"]
        self.url = f"/api/v1/sessions/{sid}/turns"

    def test_chitchat_skips_retrieval_and_summary(self):
        with patch("app.agent.workflow.search_clauses") as search:
            text = self.api.post(self.url, json={"message": "你好"}).text
        search.assert_not_called()
        self.assertIn("意图识别：chitchat", text)
        self.assertIn("排水管道规程助手", text)
        self.assertIn("event: answer", text)
        self.assertIn("CJJ 181", text)
        self.assertNotIn("ReAct：LLM 总结输出", text)

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
        with patch(
            "app.agent.workflow.search_clauses", return_value={"evidence": evidence}
        ):
            text = self.api.post(
                self.url,
                json={
                    "message": "CCTV 与 QV 的适用条件有何差异？",
                },
            ).text
        self.assertIn("event: plan_step", text)
        self.assertIn("2.1.1", text)
        self.assertIn("CCTV", text)
        self.assertIn("QV", text)
        self.assertIn("ReAct：检索总结", text)

    def test_plan_without_evidence_refuses(self):
        with patch("app.agent.workflow.search_clauses", return_value={"evidence": []}):
            text = self.api.post(
                self.url,
                json={"message": "请给出检测方案。"},
            ).text
        self.assertIn(REFUSAL, text)

    def test_kn04_no_evidence(self):
        with patch("app.agent.workflow.search_clauses", return_value={"evidence": []}):
            self.assertIn(
                REFUSAL, self.api.post(self.url, json={"message": "库外问题"}).text
            )

    def test_search_does_not_call_mcp(self):
        with patch(
            "app.agent.workflow.search_clauses", return_value={"evidence": []}
        ) as search:
            self.api.post(self.url, json={"message": "第1.0.1条写了什么？"})
            search.assert_called_once()

    def test_index_question_uses_retrieval_not_mcp(self):
        with patch(
            "app.agent.workflow.search_clauses", return_value={"evidence": []}
        ) as search:
            text = self.api.post(self.url, json={"message": "计算养护指数"}).text
        search.assert_called()
        self.assertIn("进入 ReAct 检索", text)
        self.assertIn("ReAct：检索总结", text)
        self.assertNotIn("get_calculation_schema", text)
        self.assertNotIn("clarification_required", text)
