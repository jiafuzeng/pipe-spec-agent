"""Capture the nine task questions against a running workbench API."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from agentEval.run import parse_sse


def capture(client):
    questions = json.loads(
        Path(__file__).with_name("agent_validation.json").read_bytes()
    )["cases"]
    rows = []
    for case in questions:
        if not case["id"].startswith("SPEC-"):
            continue
        session = client.post("/api/v1/sessions")
        session.raise_for_status()
        sid = session.json()["session_id"]
        response = client.post(
            f"/api/v1/sessions/{sid}/turns", json={"message": case["query"]}
        )
        response.raise_for_status()
        events = parse_sse(response.text)
        rows.append(
            dict(case=case["id"], question=case["query"], session_id=sid, events=events)
        )
    return dict(captured_at=datetime.now(timezone.utc).isoformat(), cases=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with httpx.Client(base_url=args.api, timeout=180) as client:
        result = capture(client)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
