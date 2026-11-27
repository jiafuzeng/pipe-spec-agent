"""Transactional index publication. One active version per source."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
    CREATE TABLE IF NOT EXISTS source_documents (
        source_doc_id TEXT PRIMARY KEY, original_filename TEXT, title TEXT, edition TEXT,
        sha256 TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS chunks (
        job TEXT, chunk_index INTEGER, node_id TEXT, text TEXT, metadata TEXT,
        PRIMARY KEY(job,chunk_index));
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, source TEXT, version TEXT, config TEXT,
        state TEXT, count INTEGER DEFAULT 0, error TEXT,
        created TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(source,version));
    CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, source TEXT, version TEXT);
    CREATE TABLE IF NOT EXISTS audit (
        job TEXT, action TEXT, actor TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def knowledge_root():
    configured = Path(os.getenv("KNOWLEDGE_DIR", "data/knowledge")).expanduser()
    if not configured.is_absolute():
        configured = Path.cwd() / configured
    return configured.resolve()


class Registry:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "registry.sqlite"
        with self.connect():
            pass

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.executescript(SCHEMA)
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, source, version, config, key=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO source_documents(source_doc_id,original_filename,title,edition,sha256) VALUES(?,?,?,?,?)",
                (
                    source,
                    config.get("original_filename"),
                    config.get("title"),
                    config.get("edition"),
                    source,
                ),
            )
            if key:
                db.execute(
                    "INSERT OR IGNORE INTO requests VALUES(?,?,?)",
                    (key, source, version),
                )
                binding = db.execute(
                    "SELECT source,version FROM requests WHERE key=?", (key,)
                ).fetchone()
                if tuple(binding) != (source, version):
                    raise ValueError("幂等键已绑定其他导入参数")
            row = db.execute(
                "SELECT id,state FROM jobs WHERE source=? AND version=?",
                (source, version),
            ).fetchone()
            if row and row["state"] not in {"failed", "deleted"}:
                return row["id"], False
            job = uuid.uuid4().hex
            if row:
                db.execute("UPDATE jobs SET version=id WHERE id=?", (row["id"],))
            db.execute(
                "INSERT INTO jobs(id,source,version,config,state) VALUES(?,?,?,?,?)",
                (job, source, version, json.dumps(config), "queued"),
            )
            return job, True

    def stage(self, job, state):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET state=? WHERE id=? AND state IN ('queued','parsing','chunking','embedding')",
                (state, job),
            ).rowcount
            if not changed:
                raise ValueError("任务已结束")

    def finish(self, job, count, nodes=()):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET state='built_pending_review',count=? WHERE id=? AND state!='deleted'",
                (count, job),
            ).rowcount
            if not changed:
                raise ValueError("任务已撤销")
            db.executemany(
                "INSERT INTO chunks VALUES(?,?,?,?,?)",
                (
                    (
                        job,
                        i,
                        node.id_,
                        node.text,
                        json.dumps(
                            {"page_printed": None, "page_pdf": None, "clause_no": None}
                            | node.metadata,
                            ensure_ascii=False,
                        ),
                    )
                    for i, node in enumerate(nodes)
                ),
            )

    def fail(self, job, error):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET state='failed',error=? WHERE id=? AND state!='deleted'",
                (error, job),
            )

    def approve(self, job, actor):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT source FROM jobs WHERE id=? AND state='built_pending_review'",
                (job,),
            ).fetchone()
            if not row or not actor.strip():
                raise ValueError("需要待审核版本和审核人")
            db.execute(
                "UPDATE jobs SET state='superseded' WHERE source=? AND state='active_approved'",
                (row[0],),
            )
            db.execute("UPDATE jobs SET state='active_approved' WHERE id=?", (job,))
            db.execute(
                "INSERT INTO audit(job,action,actor) VALUES(?,'approve',?)",
                (job, actor),
            )

    def delete(self, source):
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit(job,action) SELECT id,'delete' FROM jobs WHERE source=?",
                (source,),
            )
            db.execute("UPDATE jobs SET state='deleted' WHERE source=?", (source,))

    def jobs(self):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM jobs ORDER BY rowid DESC")
            ]

    def active(self):
        return [row for row in self.jobs() if row["state"] == "active_approved"]
