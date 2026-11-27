"""SQLite state and ordered event journal for single-worker execution."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("AGENT_DB", "data/agent/app.sqlite"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created_at TEXT, title TEXT);
                CREATE TABLE IF NOT EXISTS subjects(sid TEXT, id TEXT, version INTEGER, body TEXT,
                                                  PRIMARY KEY(sid,id));
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, sid TEXT, subject TEXT,
                                                status TEXT, last_error TEXT);
                CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY, run TEXT, message TEXT,
                                                 created_at TEXT);
                CREATE TABLE IF NOT EXISTS run_events(run TEXT, seq INTEGER, payload TEXT,
                                                     PRIMARY KEY(run,seq));
                CREATE TABLE IF NOT EXISTS checkpoints(turn TEXT PRIMARY KEY, next_node TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY, run TEXT, tool TEXT,
                                                 inputs TEXT, output TEXT, status TEXT);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            if "title" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN title TEXT")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        sid, created = uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions(id, created_at) VALUES(?,?)", (sid, created)
            )
        return dict(session_id=sid, created_at=created, state="ready")

    def list_sessions(self):
        with self.connect() as db:
            rows = db.execute(
                """SELECT session_id, title, last_message, last_activity_at FROM (
                       SELECT sessions.id AS session_id,
                              sessions.title AS title,
                              (SELECT turns.message FROM turns
                               JOIN runs ON runs.id = turns.run
                               WHERE runs.sid = sessions.id
                               ORDER BY turns.rowid DESC LIMIT 1) AS last_message,
                              (SELECT turns.created_at FROM turns
                               JOIN runs ON runs.id = turns.run
                               WHERE runs.sid = sessions.id
                               ORDER BY turns.rowid DESC LIMIT 1) AS last_activity_at
                       FROM sessions
                   )
                   WHERE last_message IS NOT NULL
                   ORDER BY last_activity_at DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    def rename(self, sid, title):
        title = title.strip()
        with self.connect() as db:
            found = db.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
            if found is None:
                return None
            db.execute("UPDATE sessions SET title=? WHERE id=?", (title, sid))
        return dict(session_id=sid, title=title)

    def delete(self, sid):
        with self.connect() as db:
            if db.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone() is None:
                return False
            runs = [row[0] for row in db.execute("SELECT id FROM runs WHERE sid=?", (sid,))]
            if runs:
                marks = ",".join("?" * len(runs))
                db.execute(f"DELETE FROM steps WHERE run IN ({marks})", runs)
                db.execute(f"DELETE FROM run_events WHERE run IN ({marks})", runs)
                db.execute(
                    f"""DELETE FROM checkpoints WHERE turn IN (
                            SELECT id FROM turns WHERE run IN ({marks})
                        )""",
                    runs,
                )
                db.execute(f"DELETE FROM turns WHERE run IN ({marks})", runs)
                db.execute("DELETE FROM runs WHERE sid=?", (sid,))
            db.execute("DELETE FROM subjects WHERE sid=?", (sid,))
            db.execute("DELETE FROM sessions WHERE id=?", (sid,))
        return True

    def session(self, sid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if row is None:
                return None
            subjects = {}
            for sub in db.execute("SELECT * FROM subjects WHERE sid=?", (sid,)):
                state = json.loads(sub["body"])
                slots = state.get("slots", {})
                subjects[sub["id"]] = dict(
                    confirmed={
                        k: {n: f["value"] for n, f in v.items()}
                        for k, v in slots.items()
                    },
                    parameters=slots,
                    observations=state.get("observations", {}),
                    pending=state.get("pending"),
                    state_version=sub["version"],
                    pending_questions=state.get("missing", []),
                    active_run_id=state.get("run"),
                )
            rows = db.execute(
                """SELECT turns.id AS turn_id, run AS run_id, subject AS subject_id,
                                   message AS text FROM turns JOIN runs ON runs.id=turns.run
                                   WHERE sid=? ORDER BY turns.rowid""",
                (sid,),
            ).fetchall()
            messages = [dict(r, role="user") for r in rows]
            last = rows[-1] if rows else None
            return dict(
                session_id=sid,
                created_at=row["created_at"],
                state="ready",
                subjects=subjects,
                messages=messages,
                active_run_id=last["run_id"] if last else None,
                subject_id=last["subject_id"] if last else "default",
            )

    def subject(self, sid, subject):
        with self.connect() as db:
            row = db.execute(
                "SELECT body,version FROM subjects WHERE sid=? AND id=?", (sid, subject)
            ).fetchone()
        return (json.loads(row[0]), row[1]) if row else ({}, 0)

    def start(self, sid, subject, run, turn, query, state, version):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,'running',NULL) ON CONFLICT(id) DO UPDATE SET status='running',last_error=NULL",
                (run, sid, subject),
            )
            db.execute("INSERT INTO turns VALUES(?,?,?,?)", (turn, run, query, now()))
            db.execute(
                "INSERT OR IGNORE INTO subjects VALUES(?,?,0,'{}')", (sid, subject)
            )
            self.save(db, sid, subject, state, version)

    @staticmethod
    def save(db, sid, subject, state, version):
        updated = db.execute(
            "UPDATE subjects SET body=?, version=version+1 WHERE sid=? AND id=? AND version=?",
            (json.dumps(state, ensure_ascii=False), sid, subject, version),
        )
        if not updated.rowcount:
            raise RuntimeError("管段状态已更新")

    def event(self, run, turn, kind, data, status, state, version):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            info = db.execute(
                "SELECT sid,subject FROM runs WHERE id=?", (run,)
            ).fetchone()
            seq = db.execute(
                "SELECT COALESCE(MAX(seq),-1)+1 FROM run_events WHERE run=?", (run,)
            ).fetchone()[0]
            payload = dict(
                data,
                type=kind,
                run_id=run,
                turn_id=turn,
                event_id=seq,
                session_id=info[0],
                subject_id=info[1],
            )
            payload.setdefault("step_id", f"{turn}-{seq}")
            db.execute(
                "INSERT INTO run_events VALUES(?,?,?)",
                (run, seq, json.dumps(payload, ensure_ascii=False)),
            )
            db.execute(
                "UPDATE runs SET status=?,last_error=COALESCE(?,last_error) WHERE id=?",
                (status, data.get("code") if kind == "error" else None, run),
            )
            self.save(db, *info, state, version)
        return payload

    def record_step(self, step, run, tool, inputs, output=None):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO steps VALUES(?,?,?,?,?,?)",
                (
                    step,
                    run,
                    tool,
                    json.dumps(inputs),
                    json.dumps(output) if output else None,
                    "running"
                    if output is None
                    else "failed"
                    if "error" in output
                    else "succeeded",
                ),
            )

    def events(self, run, after=-1):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT payload FROM run_events WHERE run=? AND seq>? ORDER BY seq",
                    (run, after),
                )
            ]

    def run(self, run):
        with self.connect() as db:
            row = db.execute(
                "SELECT id AS run_id,sid AS session_id,subject AS subject_id,status,last_error FROM runs WHERE id=?",
                (run,),
            ).fetchone()
            if row is None:
                return None
            steps = db.execute(
                "SELECT id,tool,status,output FROM steps WHERE run=? ORDER BY rowid",
                (run,),
            ).fetchall()
            count = db.execute(
                "SELECT count(*) FROM run_events WHERE run=?", (run,)
            ).fetchone()[0]
        return dict(
            row,
            event_count=count,
            steps=[
                dict(r) | {"output": json.loads(r["output"] or "null")} for r in steps
            ],
        )

    def checkpoint(self, turn, next_node, state):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)",
                (turn, next_node, json.dumps(state, ensure_ascii=False)),
            )

    def restore(self, turn):
        with self.connect() as db:
            row = db.execute(
                "SELECT next_node,body FROM checkpoints WHERE turn=?", (turn,)
            ).fetchone()
            return json.loads(row[1]) | {"resume_at": row[0]} if row else None

    def completed_tool(self, step):
        with self.connect() as db:
            row = db.execute(
                "SELECT output FROM steps WHERE id=? AND status='succeeded'", (step,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def interrupted(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("""
                SELECT runs.id AS run,sid,subject,turns.id AS turn,message FROM runs
                JOIN turns ON turns.rowid=(SELECT MAX(rowid) FROM turns WHERE run=runs.id)
                WHERE status='running'""")
            ]
