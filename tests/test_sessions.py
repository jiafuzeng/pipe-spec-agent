import os
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentEval.fixture_tools import call_tool
from agentEval.run import parse_sse


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


class SessionListTests(unittest.TestCase):
    def test_list_returns_each_session_without_the_other_messages(self):
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app(tool_client=call_tool)) as api,
        ):
            first = api.post("/api/v1/sessions").json()["session_id"]
            second = api.post("/api/v1/sessions").json()["session_id"]
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{first}/turns",
                    json={"message": "第一条会话的问题"},
                ).text
            )
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{second}/turns",
                    json={"message": "第二条会话的问题"},
                ).text
            )
            listed = api.get("/api/v1/sessions").json()
            by_id = {item["session_id"]: item for item in listed}
            self.assertEqual(set(by_id), {first, second})
            self.assertEqual(by_id[first]["last_message"], "第一条会话的问题")
            self.assertEqual(by_id[second]["last_message"], "第二条会话的问题")
            self.assertNotIn("messages", by_id[first])
            opened = api.get(f"/api/v1/sessions/{first}").json()
            texts = [item["text"] for item in opened["messages"]]
            self.assertEqual(texts, ["第一条会话的问题"])
            self.assertNotIn("第二条会话的问题", texts)

    def test_list_orders_by_latest_question_and_omits_empty_sessions(self):
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app(tool_client=call_tool)) as api,
        ):
            older = api.post("/api/v1/sessions").json()["session_id"]
            newer = api.post("/api/v1/sessions").json()["session_id"]
            empty = api.post("/api/v1/sessions").json()["session_id"]
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{older}/turns",
                    json={"message": "较早的问题"},
                ).text
            )
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{newer}/turns",
                    json={"message": "另一段的问题"},
                ).text
            )
            listed = api.get("/api/v1/sessions").json()
            self.assertEqual([item["session_id"] for item in listed], [newer, older])
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{older}/turns",
                    json={"message": "较早会话的新问题"},
                ).text
            )
            listed = api.get("/api/v1/sessions").json()
            self.assertEqual([item["session_id"] for item in listed], [older, newer])
            self.assertEqual(listed[0]["last_message"], "较早会话的新问题")
            self.assertEqual(listed[1]["last_message"], "另一段的问题")
            self.assertGreaterEqual(
                listed[0]["last_activity_at"], listed[1]["last_activity_at"]
            )
            self.assertNotIn(empty, [item["session_id"] for item in listed])
            self.assertNotIn("messages", listed[0])

    def test_opened_session_returns_every_question_in_order(self):
        from app.server.routes.sessions import Store
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app(tool_client=call_tool)) as api,
        ):
            store = Store(_env(tmp)["AGENT_DB"])
            sid = store.create()["session_id"]
            version = 0
            for index in range(31):
                store.start(
                    sid,
                    "default",
                    uuid.uuid4().hex,
                    uuid.uuid4().hex,
                    f"问题{index:02d}",
                    {},
                    version,
                )
                version += 1
            opened = api.get(f"/api/v1/sessions/{sid}").json()
            texts = [item["text"] for item in opened["messages"]]
            self.assertEqual(len(texts), 31)
            self.assertEqual(texts[0], "问题00")
            self.assertEqual(texts[-1], "问题30")

    def test_rename_and_delete_keep_other_sessions(self):
        from app.server.application import create_app

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, _env(tmp)),
            TestClient(create_app(tool_client=call_tool)) as api,
        ):
            kept = api.post("/api/v1/sessions").json()["session_id"]
            gone = api.post("/api/v1/sessions").json()["session_id"]
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{kept}/turns",
                    json={"message": "保留的问题"},
                ).text
            )
            parse_sse(
                api.post(
                    f"/api/v1/sessions/{gone}/turns",
                    json={"message": "要删除的问题"},
                ).text
            )
            renamed = api.patch(
                f"/api/v1/sessions/{kept}", json={"title": "现场复查"}
            )
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(renamed.json()["title"], "现场复查")
            listed = {item["session_id"]: item for item in api.get("/api/v1/sessions").json()}
            self.assertEqual(listed[kept]["title"], "现场复查")
            self.assertEqual(listed[kept]["last_message"], "保留的问题")
            self.assertEqual(api.patch("/api/v1/sessions/missing", json={"title": "不存在"}).status_code, 404)
            removed = api.delete(f"/api/v1/sessions/{gone}")
            self.assertEqual(removed.status_code, 204)
            self.assertEqual(api.get(f"/api/v1/sessions/{gone}").status_code, 404)
            self.assertEqual(api.delete(f"/api/v1/sessions/{gone}").status_code, 404)
            after = api.get("/api/v1/sessions").json()
            self.assertEqual([item["session_id"] for item in after], [kept])
            texts = [item["text"] for item in api.get(f"/api/v1/sessions/{kept}").json()["messages"]]
            self.assertEqual(texts, ["保留的问题"])
