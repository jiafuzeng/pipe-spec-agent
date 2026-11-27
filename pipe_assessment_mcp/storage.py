"""MCP-owned SQLite results and chart artifacts (not the knowledge Registry)."""

import json
import os
import sqlite3
from pathlib import Path


def data_root() -> Path:
    raw = os.getenv("MCP_DATA_DIR")
    if raw:
        path = Path(raw)
    else:
        path = Path(__file__).resolve().parents[1] / "data" / "mcp"
    path.mkdir(parents=True, exist_ok=True)
    (path / "artifacts").mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    root = data_root()
    db = sqlite3.connect(root / "results.sqlite", check_same_thread=False)
    db.execute(
        "CREATE TABLE IF NOT EXISTS results ("
        "request TEXT PRIMARY KEY, digest TEXT NOT NULL, body TEXT NOT NULL)"
    )
    db.commit()
    return db


def save_result(idempotency_key: str, digest: str, body: dict) -> str | None:
    """Insert-or-ignore; return conflict error code if digest differs."""
    payload = json.dumps(body, ensure_ascii=False)
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO results VALUES(?,?,?)",
            (idempotency_key, digest, payload),
        )
        saved = db.execute(
            "SELECT digest FROM results WHERE request=?", (idempotency_key,)
        ).fetchone()
        if saved[0] != digest:
            return "IDEMPOTENCY_CONFLICT"
    return None


def load_results_by_digest(digests: list[str]) -> list[dict] | None:
    with connect() as db:
        rows = []
        for key in digests:
            row = db.execute(
                "SELECT body FROM results WHERE digest=? LIMIT 1", (key,)
            ).fetchone()
            if row is None:
                return None
            rows.append(json.loads(row[0]))
        return rows


def artifact_path(resource_id: str) -> Path:
    return data_root() / "artifacts" / f"{resource_id}.png"
