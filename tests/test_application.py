import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


_SKIP_CALC = unittest.skip("agent calculation flow removed")


class ApplicationTests(unittest.TestCase):
    @_SKIP_CALC
    def test_restart_resumes_subject_and_event_cursor(self):
        from app.server.application import create_app
        from agentEval.fixture_tools import call_tool
        from agentEval.run import parse_sse

        with (
            TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "AGENT_DB": str(Path(tmp) / "app.sqlite"),
                    "MCP_INLINE": "1",
                    "RULE_FIXTURE": "1",
                    "MCP_DATA_DIR": tmp,
                },
            ),
        ):
            with TestClient(create_app(tool_client=call_tool)) as api:
                url = (
                    "/api/v1/sessions/"
                    + api.post("/api/v1/sessions").json()["session_id"]
                )
                first = parse_sse(
                    api.post(
                        url + "/turns",
                        json={"subject_id": "A", "message": "计算 RI，F=6 K=0"},
                    ).text
                )
                self.assertEqual(first[-1]["type"], "clarification_required")
            with TestClient(create_app(tool_client=call_tool)) as api:
                second = parse_sse(
                    api.post(
                        url + "/turns", json={"subject_id": "A", "message": "E=6 T=0"}
                    ).text
                )
                run = first[0]["run_id"]
                self.assertEqual(second[0]["run_id"], run)
                self.assertEqual(float(second[-1]["value"]), 4.5)
                replay = api.get(
                    f"/api/v1/runs/{run}/events",
                    params={"after_event_id": first[-1]["event_id"]},
                ).json()["events"]
                self.assertEqual(replay, second)
                self.assertEqual(
                    api.get(url).json()["subjects"]["A"]["confirmed"]["RI"]["K"], "0"
                )

    @_SKIP_CALC
    def test_remote_resource_round_trip_and_subject_isolation(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from pipe_assessment_mcp.server import server
        from app.server.application import create_app
        from agentEval.run import parse_sse
        import httpx
        import json

        async def protocol_call(tool, args):
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool(tool, args)
                return json.loads(result.content[0].text)

        with (
            TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "AGENT_DB": str(Path(tmp) / "app.sqlite"),
                    "RULE_FIXTURE": "1",
                    "MCP_DATA_DIR": tmp,
                    "MCP_INLINE": "0",
                    "MCP_URL": "http://127.0.0.1:8001/mcp",
                    "AGENT_MODEL_ENABLED": "0",
                },
            ),
            patch("app.agent.workflow.call_tool", side_effect=protocol_call),
        ):
            with TestClient(create_app()) as api:
                sid = api.post("/api/v1/sessions").json()["session_id"]
                url = f"/api/v1/sessions/{sid}/turns"
                events = parse_sse(
                    api.post(
                        url,
                        json={
                            "subject_id": "A",
                            "message": "画 RI 曲线 K=0、3、6、10，F=6 E=6 T=0",
                        },
                    ).text
                )
                chart = next(e for e in events if e["type"] == "chart")
                self.assertNotIn("png_base64", json.dumps(events))
                png = "/artifacts/" + chart["resource_id"]
                transport = httpx.ASGITransport(app=server.streamable_http_app())
                factory = httpx.AsyncClient
                with patch(
                    "httpx.AsyncClient",
                    side_effect=lambda **kw: factory(transport=transport, **kw),
                ):
                    image = api.get("/api/v1" + png)
                self.assertEqual(image.status_code, 200)
                self.assertTrue(image.content.startswith(b"\x89PNG"))
                other = parse_sse(
                    api.post(url, json={"subject_id": "B", "message": "计算 RI"}).text
                )
                self.assertEqual(other[-1]["confirmed"], {})
                self.assertNotEqual(chart["run_id"], other[0]["run_id"])

    @unittest.skip("plan follow-up flow removed with agent simplification")
    def test_plan_followup_preserves_field_values(self):
        from app.server.application import create_app
        from agentEval.run import parse_sse

        evidence = [
            {
                "evidence_id": "level",
                "clause_no": "4.1.1",
                "quote": "电视检测时管内水位不宜大于管径的20%。",
                "exact": True,
            }
        ]
        with (
            TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "AGENT_DB": str(Path(tmp) / "app.sqlite"),
                    "AGENT_MODEL_ENABLED": "0",
                    "EVIDENCE_LLM_VERIFY": "0",
                },
            ),
            patch(
                "app.agent.workflow.search_clauses", return_value={"evidence": evidence}
            ),
            TestClient(create_app()) as api,
        ):
            sid = api.post("/api/v1/sessions").json()["session_id"]
            url = f"/api/v1/sessions/{sid}/turns"
            first = parse_sse(
                api.post(url, json={"message": "DN800，水位60%，请给检测方案"}).text
            )
            second = parse_sse(
                api.post(
                    url,
                    json={
                        "message": "流速0.4m/s，管段长度80m，积泥未埋没探头，无竣工资料。"
                    },
                ).text
            )
            self.assertEqual(first[0]["run_id"], second[0]["run_id"])
            self.assertIn("DN800", second[-1]["text"])
            self.assertIn("因此不能采用CCTV", second[-1]["text"])

    @_SKIP_CALC
    def test_restart_replays_only_unfinished_graph_node(self):
        from app.server.routes.sessions import Store
        from app.server.application import create_app
        from agentEval.fixture_tools import call_tool
        from unittest.mock import AsyncMock

        with (
            TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"RULE_FIXTURE": "1", "MCP_DATA_DIR": tmp}),
        ):
            store = Store(Path(tmp) / "app.sqlite")
            sid = store.create()["session_id"]
            version = "CJJ181-2012-fixture-ri-7.1"
            query = "计算 RI F=6 K=0 E=6 T=0"
            state = {"run": "run", "pending": "RI", "rule_version": version}
            store.start(sid, "A", "run", "turn", query, state, 0)

            async def seed():
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                from app.agent.workflow import compile_graph
                from app.config import langgraph_path

                path = langgraph_path(store.path)
                path.parent.mkdir(parents=True, exist_ok=True)
                async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
                    graph = compile_graph(saver)
                    await graph.aupdate_state(
                        {"configurable": {"thread_id": sid}},
                        {
                            "resume_at": "calculate",
                            "query": query,
                            "kind": "RI",
                            "schema": {"rule_version": version},
                            "values": {"F": "6", "K": "0", "E": "6", "T": "0"},
                            "active_subject_id": "A",
                        },
                        as_node="__start__",
                    )

            import asyncio

            asyncio.run(seed())
            tool = AsyncMock(side_effect=call_tool)
            with TestClient(create_app(store, tool)) as api:
                self.assertEqual(api.get("/api/v1/runs/run").status_code, 200)
            self.assertEqual(
                [c.args[0] for c in tool.await_args_list], ["calculate_index"]
            )
            self.assertEqual(store.run("run")["status"], "completed")
            self.assertEqual(float(store.events("run")[-1]["value"]), 4.5)

    @_SKIP_CALC
    def test_lost_calculation_response_reuses_idempotency_key(self):
        from app.server.application import create_app
        from agentEval.fixture_tools import call_tool
        from agentEval.run import parse_sse

        calls = []

        async def transport(tool, args):
            output = await call_tool(tool, args)
            if tool == "calculate_index":
                calls.append((args["idempotency_key"], output["result_id"]))
                if len(calls) == 1:
                    raise TimeoutError()
            return output

        with (
            TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "AGENT_DB": str(Path(tmp) / "agent.sqlite"),
                    "MCP_DATA_DIR": tmp,
                    "RULE_FIXTURE": "1",
                },
            ),
            TestClient(create_app(tool_client=transport)) as api,
        ):
            sid = api.post("/api/v1/sessions").json()["session_id"]
            events = parse_sse(
                api.post(
                    f"/api/v1/sessions/{sid}/turns",
                    json={"message": "计算 RI F=6 K=0 E=6 T=0"},
                ).text
            )
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0], calls[1])
            self.assertEqual(events[-1]["result_id"], calls[0][1])
            self.assertEqual(events[-2]["attempts"], 2)
