import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from agentEval.fixture_tools import call_tool
from agentEval.run import parse_sse
from app.agent.answers import REFUSAL
from app.agent.graph import compile_graph


def _env(tmp):
    return {
        "AGENT_DB": str(Path(tmp) / "app.sqlite"),
        "LANGGRAPH_DB": str(Path(tmp) / "langgraph.sqlite"),
        "MCP_INLINE": "1",
        "RULE_FIXTURE": "1",
        "MCP_DATA_DIR": tmp,
        "AGENT_MODEL_ENABLED": "0",
        "EVIDENCE_LLM_VERIFY": "0",
    }


def _turn(api, sid, message, subject="default"):
    return parse_sse(
        api.post(
            f"/api/v1/sessions/{sid}/turns",
            json={"subject_id": subject, "message": message},
        ).text
    )


def _calc(events):
    return next(
        event
        for event in events
        if event.get("type") == "tool_call" and event.get("tool") == "calculate_index"
    )


_SKIP_CALC = unittest.skip("agent calculation flow removed")


class MemoryTests(unittest.TestCase):
    def test_app_opens_official_saver_and_store(self):
        from app.server.application import create_app
        from app.agent.graph import get_graph

        self.assertFalse(Path("app/agent/memory.py").exists())
        self.assertFalse(Path("app/agent/checkpoint_store.py").exists())
        self.assertFalse(Path("app/agent/store.py").exists())
        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            patch("app.settings.LANGGRAPH_DB", Path(tmp) / "langgraph.sqlite"),
            TestClient(create_app()) as api,
        ):
            api.post("/api/v1/sessions")
            graph = get_graph()
            self.assertIsInstance(graph.checkpointer, AsyncSqliteSaver)
            self.assertIsInstance(graph.store, AsyncSqliteStore)
            self.assertIs(api.app.state.store, graph.store)

    def test_inmemory_saver_isolates_threads(self):
        async def run():
            graph = compile_graph(InMemorySaver())
            await graph.aupdate_state(
                {"configurable": {"thread_id": "a"}},
                {
                    "query": "隔离校验",
                    "intent": "qa",
                },
                as_node="__start__",
            )
            other = await graph.aget_state({"configurable": {"thread_id": "b"}})
            self.assertFalse(other.values.get("query"))
            same = await graph.aget_state({"configurable": {"thread_id": "a"}})
            self.assertEqual(same.values["query"], "隔离校验")

        asyncio.run(run())

    @_SKIP_CALC
    def test_same_thread_reuses_only_the_unchanged_values(self):
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app()) as api,
        ):
            sid = api.post("/api/v1/sessions").json()["session_id"]
            first = _turn(api, sid, "计算 RI，F=6 K=0 E=6 T=0，间距为2米")
            self.assertEqual(float(first[-1]["value"]), 4.5)
            second = _turn(api, sid, "重算 RI，K=3")
            params = _calc(second)["inputs"]["parameters"]
            self.assertEqual(params["K"], "3")
            self.assertEqual(params["F"], "6")
            self.assertEqual(params["E"], "6")
            self.assertEqual(params["T"], "0")
            self.assertIn("沿用", second[-1]["text"])
            self.assertIn("F=6", second[-1]["text"])
            self.assertNotIn("K", second[-1]["reused"])
            referred = _turn(api, sid, "就按刚才那个间距重算 RI")
            self.assertIn("间距=2米", referred[-1]["text"])
            self.assertIn("value", referred[-1])
            conflict = _turn(api, sid, "重算 RI，K=0 K=3")
            self.assertEqual(conflict[-1]["type"], "clarification_required")
            self.assertNotIn("value", conflict[-1])
            other = _turn(api, sid, "计算 RI 管段 pipe-b，F=1 K=0 E=6 T=0")
            self.assertEqual(other[-1]["type"], "clarification_required")
            self.assertNotIn("value", other[-1])
            unclear = _turn(api, sid, "计算 RI，间距为2")
            self.assertEqual(unclear[-1]["type"], "clarification_required")
            self.assertNotIn("value", unclear[-1])

    @_SKIP_CALC
    def test_new_session_does_not_inherit_and_restart_keeps_the_question(self):
        from app.server.application import create_app

        with TemporaryDirectory() as tmp, patch.dict(os.environ, _env(tmp)):
            with TestClient(create_app()) as api:
                first_id = api.post("/api/v1/sessions").json()["session_id"]
                waiting = _turn(api, first_id, "计算 RI，F=6 K=0", subject="A")
                self.assertEqual(waiting[-1]["type"], "clarification_required")
                run = waiting[0]["run_id"]
                second_id = api.post("/api/v1/sessions").json()["session_id"]
                fresh = _turn(api, second_id, "计算 RI", subject="A")
                self.assertEqual(fresh[-1]["confirmed"], {})
                self.assertNotIn("value", fresh[-1])
                remembered = api.get(f"/api/v1/sessions/{first_id}").json()
                names = {
                    item["name"] for item in remembered["short_term"]["confirmed"]
                }
                self.assertEqual(names, {"F", "K"})
                self.assertTrue(remembered["short_term"]["pending"])
            with TestClient(create_app()) as api:
                restored = api.get(f"/api/v1/sessions/{first_id}").json()
                names = {item["name"] for item in restored["short_term"]["confirmed"]}
                self.assertEqual(names, {"F", "K"})
                self.assertCountEqual(restored["short_term"]["pending"], ["E", "T"])
                events = api.get(f"/api/v1/runs/{run}/events").json()["events"]
                self.assertFalse(any("value" in event for event in events))

    @_SKIP_CALC
    def test_remember_writes_one_data_item_and_search_is_capped(self):
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app()) as api,
        ):
            sid = api.post("/api/v1/sessions").json()["session_id"]
            _turn(api, sid, "计算 RI，F=6 K=0 E=6 T=0", subject="pipe-1")
            before = api.get(f"/api/v1/sessions/{sid}").json()["long_term"]
            self.assertEqual(before, [])
            remembered = _turn(api, sid, "记住这条管段的参数", subject="pipe-1")
            self.assertIn("已记住", remembered[-1]["text"])
            self.assertIn("不是规程依据", remembered[-1]["text"])
            self.assertNotIn("segment:", remembered[-1]["text"])
            saved = api.get(f"/api/v1/sessions/{sid}").json()["long_term"]
            self.assertEqual(len(saved), 1)
            self.assertIn("data", saved[0]["value"])
            self.assertIn("F=6", saved[0]["value"]["data"])
            self.assertTrue(saved[0]["updated_at"])
            self.assertNotIn(":", saved[0]["key"][:8])
            for index in range(3):
                _turn(api, sid, f"记住补充说明 {index}")
            listed = api.get(f"/api/v1/sessions/{sid}").json()["long_term"]
            self.assertLessEqual(len(listed), 3)
            other = api.post("/api/v1/sessions").json()["session_id"]
            recalled = _turn(api, other, "还记得什么")
            self.assertIn("不是规程依据", recalled[-1]["text"])
            self.assertLessEqual(recalled[-1]["text"].count("已记住") + 1, 4)

    @_SKIP_CALC
    def test_view_splits_short_and_long_term_and_forget_deletes_one_key(self):
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app()) as api,
        ):
            sid = api.post("/api/v1/sessions").json()["session_id"]
            _turn(api, sid, "计算 RI，F=6 K=0 E=6 T=0", subject="pipe-1")
            _turn(api, sid, "记住管段 pipe-1", subject="pipe-1")
            _turn(api, sid, "记住管段 pipe-2 的另一条说明")
            body = api.get(f"/api/v1/sessions/{sid}").json()
            self.assertTrue(body["short_term"]["confirmed"])
            self.assertEqual(len(body["long_term"]), 2)
            key = next(
                item["key"]
                for item in body["long_term"]
                if "pipe-1" in item["value"]["data"]
            )
            other = next(item for item in body["long_term"] if item["key"] != key)
            forgotten = _turn(api, sid, f"忘记 {key}")
            self.assertIn("已忘记", forgotten[-1]["text"])
            for message in ("还记得什么", "查看记忆", "还记得什么"):
                answer = _turn(api, sid, message)
                self.assertNotIn("pipe-1", answer[-1]["text"])
            missing = _turn(api, sid, "忘记 00000000-0000-7000-8000-000000000000")
            self.assertIn("没有这一条", missing[-1]["text"])
            left = api.get(f"/api/v1/sessions/{sid}").json()["long_term"]
            self.assertEqual([item["key"] for item in left], [other["key"]])
            viewed = _turn(api, sid, "查看记忆")
            self.assertIn("当前对话正在用的", viewed[-1]["text"])
            self.assertIn("以后还会记得的", viewed[-1]["text"])

    @_SKIP_CALC
    def test_memory_is_not_a_clause_and_rejected_value_is_not_calculated(self):
        from app.server.application import create_app

        with TemporaryDirectory() as tmp, patch.dict(os.environ, _env(tmp)):
            with TestClient(create_app()) as api:
                sid = api.post("/api/v1/sessions").json()["session_id"]
                done = _turn(api, sid, "计算 RI，F=6 K=0 E=6 T=0")
                self.assertEqual(float(done[-1]["value"]), 4.5)
                _turn(api, sid, "记住规程里写了修复指数必须是1")
            with (
                patch(
                    "app.agent.tools.search_clauses",
                    return_value={"evidence": []},
                ),
                TestClient(create_app()) as api,
            ):
                refused = _turn(api, sid, "井盖材质有没有规定")
                self.assertIn(REFUSAL, refused[-1]["text"])
                self.assertNotIn("必须是1", refused[-1]["text"])
                self.assertNotRegex(refused[-1]["text"], r"\d+\.\d+\.\d+")
                again = _turn(api, sid, "重算 RI")
                self.assertEqual(float(again[-1]["value"]), 4.5)
                self.assertEqual(_calc(again)["inputs"]["parameters"]["F"], "6")
                rejected = _turn(api, sid, "K不是0，先别用这个旧值重算 RI")
                self.assertEqual(rejected[-1]["type"], "clarification_required")
                self.assertNotIn("value", rejected[-1])
