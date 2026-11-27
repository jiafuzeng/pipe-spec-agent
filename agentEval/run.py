"""Agent evaluation runner — same entry as Web (rag.dialogue via rag.web)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from decimal import Decimal
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).resolve().parent / "agent_cases.json"
REPORT = Path(__file__).resolve().parent / "last_report.json"


def parse_sse(text: str) -> list[dict]:
    events = []
    kind = None
    data_lines = []
    for line in text.splitlines():
        if line.startswith("event:"):
            kind = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
        elif line == "" and data_lines:
            raw = "\n".join(data_lines)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw}
            if isinstance(payload, dict) and kind and "type" not in payload:
                payload["type"] = kind
            events.append(payload)
            kind = None
            data_lines = []
    if data_lines:
        raw = "\n".join(data_lines)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        if isinstance(payload, dict) and kind and "type" not in payload:
            payload["type"] = kind
        events.append(payload)
    return events


def infer_action(events: list[dict]) -> str:
    types = [e.get("type") for e in events]
    if any(e.get("code") == "RULE_NOT_PUBLISHED" for e in events):
        return "block_unreviewed"
    if any(e.get("action") == "block_unreviewed" for e in events):
        return "block_unreviewed"
    answers = [e for e in events if e.get("type") == "answer"]
    answer_blob = json.dumps(answers, ensure_ascii=False)
    if answers and REFUSAL_SNIPPET in answer_blob:
        if any(e.get("citations") for e in answers if e.get("citations")) or any(
            e.get("type") == "evidence" for e in events
        ):
            return "partial_answer"
        return "refuse"
    if "chart" in types:
        return "calculate_and_plot"
    if "clarification_required" in types:
        if any(e.get("type") == "evidence" for e in events) or any(
            e.get("tool") == "search_clauses"
            for e in events
            if e.get("type") == "tool_call"
        ):
            return "clarify_then_explain"
        return "clarify"
    if "answer" in types:
        return "answer"
    return "unknown"


REFUSAL_SNIPPET = "依据 CJJ 181—2012 原文无相关规定，不作推测性补充。"


def count_tools(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        if e.get("type") != "tool_call":
            continue
        name = e.get("tool")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def score_turn(expect: dict, events: list[dict], prior_run_id: str | None) -> list[str]:
    failures = []
    action = infer_action(events)
    if expect.get("action") and action != expect["action"]:
        # allow clarify_then_explain when expect clarify if groups present? keep strict
        failures.append(f"action expected {expect['action']} got {action}")

    if expect.get("first_event_fields") and events:
        first = events[0]
        for field in expect["first_event_fields"]:
            if field not in first or first[field] is None:
                failures.append(f"first event missing {field}")

    for kind in expect.get("events_include") or []:
        if not any(e.get("type") == kind for e in events):
            failures.append(f"missing event {kind}")

    tools = count_tools(events)
    for name, want in (expect.get("tool_calls") or {}).items():
        got = tools.get(name, 0)
        if got != want:
            failures.append(f"{name} expected {want} got {got}")

    if expect.get("search_not_via_mcp"):
        for e in events:
            if e.get("type") == "tool_call" and e.get("tool") == "search_clauses":
                if e.get("via") != "in_process":
                    failures.append("search_clauses must be in_process")
            if (
                e.get("type") == "tool_call"
                and e.get("tool") == "search_clauses"
                and e.get("via") == "mcp"
            ):
                failures.append("search via mcp")

    if expect.get("refusal_text"):
        blob = json.dumps(events, ensure_ascii=False)
        if expect["refusal_text"] not in blob:
            failures.append("refusal_text missing")

    if expect.get("citations_any_of"):
        clauses = {e.get("clause_no") for e in events if e.get("type") == "evidence"}
        if not clauses.intersection(expect["citations_any_of"]):
            failures.append("citations_any_of not matched")

    if expect.get("missing_parameter_groups"):
        clar = next(
            (e for e in events if e.get("type") == "clarification_required"), {}
        )
        groups = clar.get("missing_parameter_groups") or clar.get("groups") or []
        blob = json.dumps(clar, ensure_ascii=False)
        for group in expect["missing_parameter_groups"]:
            ok = False
            for g in groups:
                if set(group.get("any_of") or []) & set(g.get("any_of") or []):
                    ok = True
                    break
            if not ok:
                # also accept any_of tokens appearing in clarification text
                if any(tok in blob for tok in group.get("any_of") or []):
                    ok = True
            if not ok:
                failures.append(
                    f"missing_parameter_groups {group.get('id')} not covered"
                )

    if expect.get("missing_parameters"):
        clar = next(
            (e for e in events if e.get("type") == "clarification_required"), {}
        )
        blob = json.dumps(clar, ensure_ascii=False)
        for name in expect["missing_parameters"]:
            if name not in blob:
                failures.append(f"missing_parameters {name} not in clarification")

    if expect.get("results"):
        outputs = [
            e["output"]
            for e in events
            if e.get("tool") == "calculate_index" and e.get("status") == "succeeded"
        ]
        for row in expect["results"]:
            if not any(
                all(
                    Decimal(
                        str(
                            out.get("value")
                            if key == out.get("calculation_type")
                            else out["parameters"].get(key)
                        )
                    )
                    == Decimal(str(value))
                    for key, value in row.items()
                )
                for out in outputs
            ):
                failures.append(f"result {row} not found")

    if expect.get("chart", {}).get("required"):
        charts = [e for e in events if e.get("type") == "chart"]
        points = [
            e["output"].get("points", [])
            for e in events
            if e.get("tool") == "plot_curve" and e.get("status") == "succeeded"
        ]
        if (
            not charts
            or not points
            or (
                expect["chart"].get("points")
                and len(points[-1]) != expect["chart"]["points"]
            )
        ):
            failures.append("chart or expected points missing")

    if expect.get("same_run_continues") and prior_run_id and events:
        if events[0].get("run_id") != prior_run_id:
            failures.append("run_id did not continue")

    if expect.get("idempotent_retry_same_result_id"):
        # handled by caller with second request
        pass

    if expect.get("partial"):
        blob = json.dumps(events, ensure_ascii=False)
        if REFUSAL_SNIPPET not in blob:
            failures.append("partial refuse snippet missing")
        if not any(e.get("type") == "evidence" for e in events) and "9.0.1" not in blob:
            # soft: at least refusal + some answer structure
            pass

    return failures


def observe_turn(turn, events, failures, action, rule_mode, versions):
    expect = turn.get("expect") or {}
    answers = [
        e.get("text") for e in events if e.get("type") == "answer" and e.get("text")
    ]
    citations = [
        {
            "clause": e.get("clause_no"),
            "page": e.get("page_pdf"),
            "quote": e.get("quote"),
        }
        for e in events
        if e.get("type") == "evidence" and e.get("clause_no")
    ]
    clar = next((e for e in events if e.get("type") == "clarification_required"), None)
    results = []
    for e in events:
        if e.get("tool") != "calculate_index" or e.get("status") != "succeeded":
            continue
        output = e.get("output") or {}
        results.append(
            {
                "type": output.get("calculation_type"),
                "parameters": output.get("parameters"),
                "value": output.get("value"),
            }
        )
    charts = [
        {
            "points": len((e.get("output") or {}).get("points") or []),
            "resource_id": (e.get("output") or {}).get("resource_id"),
        }
        for e in events
        if e.get("tool") == "plot_curve" and e.get("status") == "succeeded"
    ]
    kept = {
        key: expect[key]
        for key in (
            "action",
            "tool_calls",
            "citations_any_of",
            "missing_parameters",
            "missing_parameter_groups",
            "results",
            "refusal_text",
            "events_include",
            "chart",
        )
        if key in expect
    }
    return {
        "message": turn.get("message"),
        "expect": kept,
        "action": action,
        "tools": count_tools(events),
        "citations": citations,
        "answer": "\n".join(answers),
        "clarification": None
        if clar is None
        else {
            "fields": [
                field.get("label_zh") or field.get("name")
                for field in clar.get("fields") or []
            ],
            "groups": clar.get("groups") or clar.get("missing_parameter_groups") or [],
        },
        "results": results,
        "charts": charts,
        "rule_mode": rule_mode,
        "rule_versions": versions,
        "passed": not failures,
        "failures": failures,
    }


def prepare_env(case: dict) -> dict:
    """Return env overrides for this case; caller applies/restores."""
    pre = case.get("precondition") or {}
    env = {}
    env["EVIDENCE_LLM_VERIFY"] = "0"
    env["AGENT_MODEL_ENABLED"] = "0"
    env["MCP_INLINE"] = "1"
    if pre.get("fixture_rules") or pre.get("rules") == "approved":
        env["RULE_FIXTURE"] = "1"
    else:
        env["RULE_FIXTURE"] = "0"
    if pre.get("mcp") == "offline":
        env["MCP_URL"] = "offline"
        env["MCP_INLINE"] = "0"
    return env


def apply_env(overrides: dict) -> dict:
    previous = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return previous


def restore_env(previous: dict) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _smoke_search(query: str, top_k: int = 5) -> dict:
    """Controlled retrieval fixture for graph contract tests."""
    evidence = []
    if "1.0.1" in query or "编制目的" in query:
        evidence.append(
            {
                "evidence_id": "stub-1.0.1",
                "clause_no": "1.0.1",
                "quote": "为加强城镇排水管道检测与评估管理，规范检测技术，统一评估标准，制定本规程。",
                "page_pdf": 1,
                "exact": True,
            }
        )
    if "检查井" in query or "9.0.1" in query:
        evidence.append(
            {
                "evidence_id": "stub-9.0.1",
                "clause_no": "9.0.1",
                "quote": "检查井检测应在管道检测前进行。",
                "page_pdf": 40,
                "exact": True,
            }
        )
    if "计算公式" in query:
        evidence.append(
            dict(
                evidence_id="fixture-K",
                clause_no="8.3.4",
                quote="K——地区重要性参数，可按表 8.3.4-1 的规定确定；",
                exact=True,
            )
        )
    return {"evidence": evidence}


def run_suite(suite: str = "ci") -> dict:
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.server.application import create_app
    from app.agent.store import Store
    from agentEval.fixture_tools import call_tool

    payload = json.loads(CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if suite == "ci":
        cases = [c for c in cases if c.get("ci")]
    elif suite != "all":
        cases = [c for c in cases if c["id"] == suite]

    with TemporaryDirectory() as tmp, patch.dict(os.environ, {"MCP_DATA_DIR": tmp}):
        app = create_app(store=Store(Path(tmp) / "agent.sqlite"), tool_client=call_tool)
        with TestClient(app) as client:
            return evaluate_cases(cases, client)


def evaluate_cases(cases, client):
    from unittest.mock import patch

    results = []
    action_ok = citation_ok = tool_ok = 0
    action_n = citation_n = tool_n = 0

    for case in cases:
        if case.get("blocked_until"):
            results.append(
                {
                    "id": case["id"],
                    "passed": True,
                    "skipped": True,
                    "reason": f"blocked_until={case['blocked_until']}",
                }
            )
            continue
        prev = apply_env(prepare_env(case))
        try:
            with patch("app.agent.workflow.search_clauses", side_effect=_smoke_search):
                sid = client.post("/api/v1/sessions").json()["session_id"]
                turn_results = []
                prior_run_id = None
                case_pass = True
                subject = (case.get("precondition") or {}).get("subject_id", "default")
                for index, turn in enumerate(case.get("turns") or []):
                    body = {"message": turn["message"], "subject_id": subject}
                    response = client.post(f"/api/v1/sessions/{sid}/turns", json=body)
                    events = parse_sse(response.text)
                    failures = score_turn(
                        turn.get("expect") or {}, events, prior_run_id
                    )
                    if (turn.get("expect") or {}).get(
                        "idempotent_retry_same_result_id"
                    ):
                        again = client.post(f"/api/v1/sessions/{sid}/turns", json=body)
                        events2 = parse_sse(again.text)
                        ids1 = [
                            e.get("output", {}).get("result_id")
                            for e in events
                            if e.get("tool") == "calculate_index"
                            and isinstance(e.get("output"), dict)
                        ]
                        ids2 = [
                            e.get("output", {}).get("result_id")
                            for e in events2
                            if e.get("tool") == "calculate_index"
                            and isinstance(e.get("output"), dict)
                        ]
                        if not ids1 or ids1 != ids2:
                            failures.append("idempotent_retry_same_result_id failed")

                    if events:
                        prior_run_id = events[0].get("run_id")
                    versions = sorted(
                        {
                            e["output"]["rule_version"]
                            for e in events
                            if (e.get("output") or {}).get("rule_version")
                        }
                    )
                    ok = not failures
                    case_pass = case_pass and ok
                    rule_mode = (
                        "fixture" if os.getenv("RULE_FIXTURE") == "1" else "published"
                    )
                    observed = observe_turn(
                        turn, events, failures, infer_action(events), rule_mode, versions
                    )
                    observed["index"] = index
                    turn_results.append(observed)
                    expect = turn.get("expect") or {}
                    if expect.get("action"):
                        action_n += 1
                        if not any(f.startswith("action ") for f in failures):
                            action_ok += 1
                    if expect.get("citations_any_of") or expect.get("refusal_text"):
                        citation_n += 1
                        if not any("citation" in f or "refusal" in f for f in failures):
                            citation_ok += 1
                    if expect.get("tool_calls") is not None:
                        tool_n += 1
                        if not any(re.match(r"\w+ expected ", f) for f in failures):
                            tool_ok += 1
                results.append(
                    {
                        "id": case["id"],
                        "origin": case.get("origin"),
                        "passed": case_pass,
                        "turns": turn_results,
                    }
                )
        finally:
            restore_env(prev)

    total = len([r for r in results if not r.get("skipped")])
    passed = len([r for r in results if r.get("passed") and not r.get("skipped")])
    report = {
        "mode": "inline_mcp",
        "retrieval_mode": "fixture",
        "agent_entry": "main:app / app.agent.workflow",
        "rule_mode": "per_turn",
        "summary": {
            "total": total,
            "passed": passed,
            "action_pass_rate": (action_ok / action_n) if action_n else 1.0,
            "citation_pass_rate": (citation_ok / citation_n) if citation_n else 1.0,
            "tool_constraint_pass_rate": (tool_ok / tool_n) if tool_n else 1.0,
        },
        "results": results,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run agentEval cases against Web entry"
    )
    parser.add_argument("--suite", default="ci", help="ci | all | case id")
    parser.add_argument("--output", default=str(REPORT))
    args = parser.parse_args(argv)
    report = run_suite(args.suite)
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"passed {report['summary']['passed']}/{report['summary']['total']} → {args.output}"
    )
    for row in report["results"]:
        mark = "SKIP" if row.get("skipped") else ("OK" if row.get("passed") else "FAIL")
        print(f"  {mark} {row['id']}")
        for turn in row.get("turns") or []:
            if not turn.get("passed"):
                for fail in turn.get("failures") or []:
                    print(f"    - turn{turn['index']}: {fail}")
    return 0 if report["summary"]["passed"] == report["summary"]["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
