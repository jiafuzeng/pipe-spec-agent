import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from rag.dialogue import REFUSAL


def _fake_create_agent(*, model, tools, system_prompt):
    search = tools[0]

    class _Agent:
        async def astream(self, inputs, config=None, stream_mode=None):
            content = inputs["messages"][0]["content"]
            query = content
            if "检索查询：" in content:
                query = content.split("检索查询：", 1)[1].split("\n", 1)[0].strip()
            result = await search.ainvoke({"query": query})
            text = (
                REFUSAL
                if "未命中" in str(result)
                else "- **结论**：依据检索条款作答"
            )
            final = {"messages": [AIMessage(content=text)]}
            modes = stream_mode if isinstance(stream_mode, list) else [stream_mode]
            if "updates" in modes and "values" in modes:
                deciding = AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "search_clauses", "id": "call-1", "args": {"query": query}}
                    ],
                )
                yield ("updates", {"model": {"messages": [deciding]}})
                yield ("updates", {"tools": {}})
                yield ("updates", {"model": {"messages": [AIMessage(content=text)]}})
                yield ("values", final)
            else:
                yield final

    return _Agent()


class TurnTests(unittest.TestCase):
    def setUp(self):
        from app.server.application import create_app

        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = patch.dict(
            "os.environ",
            {"LANGGRAPH_DB": str(Path(self._tmp.name) / "langgraph.sqlite")},
        )
        env.start()
        self.addCleanup(env.stop)
        agent = patch(
            "app.agent.utils.agent.create_agent",
            side_effect=_fake_create_agent,
        )
        agent.start()
        self.addCleanup(agent.stop)
        rewrite = patch(
            "app.agent.workflow.rewrite_query",
            side_effect=lambda q, intent: q,
        )
        rewrite.start()
        self.addCleanup(rewrite.stop)

        async def _pass_validate(query, draft, evidence):
            return draft, evidence, []

        validate = patch(
            "app.agent.workflow.validate_answer",
            side_effect=_pass_validate,
        )
        validate.start()
        self.addCleanup(validate.stop)
        self._client_cm = TestClient(create_app())
        self.api = self._client_cm.__enter__()
        self.addCleanup(self._client_cm.__exit__, None, None, None)
        sid = self.api.post("/api/v1/sessions").json()["session_id"]
        self.url = f"/api/v1/sessions/{sid}/turns"

    def test_chitchat_skips_retrieval_and_summary(self):
        with patch("app.agent.tools.search_clauses") as search:
            text = self.api.post(self.url, json={"message": "你好"}).text
        search.assert_not_called()
        self.assertIn("意图识别：闲聊（chitchat）", text)
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
            "app.agent.tools.search_clauses", return_value={"evidence": evidence}
        ):
            text = self.api.post(
                self.url,
                json={
                    "message": "CCTV 与 QV 的适用条件有何差异？",
                },
            ).text
        self.assertIn("event: plan_step", text)
        self.assertIn("问题改写为检索查询", text)
        self.assertIn("模型决定调用工具", text)
        self.assertIn("event: tool_call", text)
        self.assertIn("工具结果已回传", text)
        self.assertIn("模型依据检索结果整理回答", text)
        self.assertIn("2.1.1", text)
        self.assertIn("CCTV", text)
        self.assertIn("QV", text)
        self.assertIn("回答校验", text)

    def test_plan_without_evidence_refuses(self):
        with patch("app.agent.tools.search_clauses", return_value={"evidence": []}):
            text = self.api.post(
                self.url,
                json={"message": "请给出检测方案。"},
            ).text
        self.assertIn(REFUSAL, text)

    def test_kn04_no_evidence(self):
        with patch("app.agent.tools.search_clauses", return_value={"evidence": []}):
            self.assertIn(
                REFUSAL, self.api.post(self.url, json={"message": "库外问题"}).text
            )

    def test_search_does_not_call_mcp(self):
        with patch(
            "app.agent.tools.search_clauses", return_value={"evidence": []}
        ) as search:
            self.api.post(self.url, json={"message": "第1.0.1条写了什么？"})
            search.assert_called_once()

    def test_index_question_uses_retrieval_not_mcp(self):
        with patch(
            "app.agent.tools.search_clauses", return_value={"evidence": []}
        ) as search:
            text = self.api.post(self.url, json={"message": "计算养护指数"}).text
        search.assert_called()
        self.assertIn("问题改写为检索查询", text)
        self.assertIn("回答校验", text)
        self.assertNotIn("get_calculation_schema", text)
        self.assertNotIn("clarification_required", text)

    def test_react_recursion_falls_back_to_evidence(self):
        from langgraph.errors import GraphRecursionError

        class _Looping:
            async def astream(self, inputs, config=None, stream_mode=None):
                yield ("updates", {"tools": {}})
                raise GraphRecursionError("Recursion limit of 10 reached")

        evidence = [
            {
                "evidence_id": "p1",
                "clause_no": "1.0.1",
                "quote": "1.0.1 为加强城镇排水管道检测管理，制定本规程。",
            }
        ]
        with (
            patch(
                "app.agent.utils.agent.create_agent",
                return_value=_Looping(),
            ),
            patch(
                "app.agent.tools.search_clauses",
                return_value={"evidence": evidence},
            ),
        ):
            text = self.api.post(
                self.url,
                json={"message": "编制目的是什么？"},
            ).text
        self.assertNotIn("TOOL_UNAVAILABLE", text)
        self.assertIn("达到步数上限", text)
        self.assertIn("event: answer", text)

    def test_react_timeout_falls_back_to_evidence(self):
        class _TimedOut:
            async def astream(self, inputs, config=None, stream_mode=None):
                yield ("updates", {"tools": {}})
                raise TimeoutError("Request timed out.")

        evidence = [
            {
                "evidence_id": "p1",
                "clause_no": "1.0.1",
                "quote": "1.0.1 为加强城镇排水管道检测管理，制定本规程。",
            }
        ]
        with (
            patch(
                "app.agent.utils.agent.create_agent",
                return_value=_TimedOut(),
            ),
            patch(
                "app.agent.tools.search_clauses",
                return_value={"evidence": evidence},
            ),
        ):
            text = self.api.post(
                self.url,
                json={"message": "编制目的是什么？"},
            ).text
        self.assertNotIn("TOOL_UNAVAILABLE", text)
        self.assertIn("模型超时", text)
        self.assertIn("event: answer", text)
