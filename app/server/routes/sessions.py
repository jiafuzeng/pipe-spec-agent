import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from langgraph.store.sqlite import SqliteStore
from pydantic import BaseModel, Field

from app.agent.workflow import get_graph

router = APIRouter()
log = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Session / run / event persistence on LangGraph SqliteStore."""

    def __init__(self, path=None):
        from app.settings import agent_db

        self.path = Path(path or agent_db())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        self._db = SqliteStore(self._conn)
        self._db.setup()

    def close(self):
        self._conn.close()

    def create(self):
        sid, created = uuid.uuid4().hex, _now()
        self._db.put(
            ("app", "sessions"),
            sid,
            {
                "created_at": created,
                "title": None,
                "last_message": None,
                "last_activity_at": None,
            },
        )
        return dict(session_id=sid, created_at=created, state="ready")

    def list_sessions(self):
        rows = []
        for item in self._db.search(("app", "sessions"), limit=1000):
            value = item.value or {}
            if not value.get("last_message"):
                continue
            rows.append(
                dict(
                    session_id=item.key,
                    title=value.get("title"),
                    last_message=value.get("last_message"),
                    last_activity_at=value.get("last_activity_at")
                    or value.get("created_at"),
                )
            )
        rows.sort(key=lambda row: row["last_activity_at"] or "", reverse=True)
        return rows

    def rename(self, sid, title):
        title = title.strip()
        item = self._db.get(("app", "sessions"), sid)
        if item is None:
            return None
        value = dict(item.value or {})
        value["title"] = title
        self._db.put(("app", "sessions"), sid, value)
        return dict(session_id=sid, title=title)

    def delete(self, sid):
        if self._db.get(("app", "sessions"), sid) is None:
            return False
        for run in self._db.search(("app", "runs"), filter={"sid": sid}, limit=1000):
            for event in self._db.search(("app", "events", run.key), limit=10000):
                self._db.delete(("app", "events", run.key), event.key)
            self._db.delete(("app", "runs"), run.key)
        for subject in self._db.search(("app", "subjects", sid), limit=1000):
            self._db.delete(("app", "subjects", sid), subject.key)
        for turn in self._db.search(("app", "turns", sid), limit=10000):
            self._db.delete(("app", "turns", sid), turn.key)
        self._db.delete(("app", "sessions"), sid)
        return True

    def session(self, sid):
        item = self._db.get(("app", "sessions"), sid)
        if item is None:
            return None
        turns = sorted(
            self._db.search(("app", "turns", sid), limit=10000),
            key=lambda row: (row.value or {}).get("created_at") or row.key,
        )
        messages = [
            dict(
                turn_id=turn.key,
                run_id=(turn.value or {}).get("run"),
                subject_id=(turn.value or {}).get("subject") or "default",
                text=(turn.value or {}).get("message") or "",
                role="user",
            )
            for turn in turns
        ]
        last = messages[-1] if messages else None
        return dict(
            session_id=sid,
            created_at=(item.value or {}).get("created_at"),
            state="ready",
            subjects={},
            messages=messages,
            active_run_id=last["run_id"] if last else None,
            subject_id=last["subject_id"] if last else "default",
        )

    def subject(self, sid, subject):
        item = self._db.get(("app", "subjects", sid), subject)
        if item is None:
            return {}, 0
        value = item.value or {}
        return dict(value.get("body") or {}), int(value.get("version") or 0)

    def start(self, sid, subject, run, turn, query, state, version):
        self._db.put(
            ("app", "runs"),
            run,
            {
                "sid": sid,
                "subject": subject,
                "status": "running",
                "last_error": None,
                "turn": turn,
                "message": query,
                "event_seq": -1,
            },
        )
        created = _now()
        self._db.put(
            ("app", "turns", sid),
            turn,
            {"run": run, "message": query, "created_at": created, "subject": subject},
        )
        session = self._db.get(("app", "sessions"), sid)
        if session is not None:
            value = dict(session.value or {})
            value["last_message"] = query
            value["last_activity_at"] = created
            self._db.put(("app", "sessions"), sid, value)
        if self._db.get(("app", "subjects", sid), subject) is None:
            self._db.put(("app", "subjects", sid), subject, {"body": {}, "version": 0})
        self._save(sid, subject, state, version)

    def _save(self, sid, subject, state, version):
        item = self._db.get(("app", "subjects", sid), subject)
        current = int((item.value or {}).get("version") or 0) if item else 0
        if current != version:
            raise RuntimeError("管段状态已更新")
        self._db.put(
            ("app", "subjects", sid),
            subject,
            {"body": state, "version": version + 1},
        )

    def event(self, run, turn, kind, data, status, state, version):
        item = self._db.get(("app", "runs"), run)
        if item is None:
            raise RuntimeError("run 不存在")
        info = item.value or {}
        seq = int(info.get("event_seq") or -1) + 1
        payload = dict(
            data,
            type=kind,
            run_id=run,
            turn_id=turn,
            event_id=seq,
            session_id=info.get("sid"),
            subject_id=info.get("subject"),
        )
        payload.setdefault("step_id", f"{turn}-{seq}")
        self._db.put(("app", "events", run), f"{seq:08d}", payload)
        info = dict(info)
        info["event_seq"] = seq
        info["status"] = status
        if kind == "error":
            info["last_error"] = data.get("code")
        self._db.put(("app", "runs"), run, info)
        self._save(info["sid"], info["subject"], state, version)
        return payload

    def events(self, run, after=-1):
        rows = sorted(
            self._db.search(("app", "events", run), limit=10000),
            key=lambda item: item.key,
        )
        return [
            item.value
            for item in rows
            if int((item.value or {}).get("event_id", -1)) > after
        ]

    def run(self, run):
        item = self._db.get(("app", "runs"), run)
        if item is None:
            return None
        info = item.value or {}
        return dict(
            run_id=run,
            session_id=info.get("sid"),
            subject_id=info.get("subject"),
            status=info.get("status"),
            last_error=info.get("last_error"),
            event_count=int(info.get("event_seq") or -1) + 1,
        )


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    subject_id: str = Field(default="default", min_length=1, max_length=128)


class SessionTitle(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class Execution:
    def __init__(self, store):
        self.store = store
        self.locks = WeakValueDictionary()

    async def stream(self, sid, subject, query):
        """Run one turn; persist LangGraph custom events and yield them for SSE."""
        lock = self.locks.setdefault((sid, subject), asyncio.Lock())
        async with lock:
            state, version = self.store.subject(sid, subject)
            run_id = uuid.uuid4().hex
            turn_id = uuid.uuid4().hex
            state.update(run=run_id, subject_id=subject)
            self.store.start(sid, subject, run_id, turn_id, query, state, version)
            version += 1
            graph = get_graph()
            config = (
                {"configurable": {"thread_id": sid}} if graph.checkpointer else None
            )
            try:
                stream = graph.astream(
                    {"query": query},
                    config=config,
                    stream_mode="custom",
                )
                async for chunk in stream:
                    if not isinstance(chunk, dict) or not chunk.get("type"):
                        continue
                    kind = chunk["type"]
                    status = chunk.get("status") or "running"
                    data = {
                        key: value
                        for key, value in chunk.items()
                        if key not in {"type", "status"}
                    }
                    event = self.store.event(
                        run_id, turn_id, kind, data, status, state, version
                    )
                    version += 1
                    yield event
            except Exception:
                log.exception("Turn %s failed", turn_id)
                yield self.store.event(
                    run_id,
                    turn_id,
                    "error",
                    dict(
                        code="TOOL_UNAVAILABLE",
                        text="执行中断，可重新提交。",
                        retryable=True,
                    ),
                    "failed",
                    state,
                    version,
                )


def service(request):
    if not hasattr(request.app.state, "execution"):
        request.app.state.execution = Execution(Store())
    return request.app.state.execution


@router.post("/api/v1/sessions")
async def create_session(request: Request):
    return service(request).store.create()


@router.get("/api/v1/sessions")
async def list_sessions(request: Request):
    return service(request).store.list_sessions()


@router.patch("/api/v1/sessions/{sid}")
async def rename_session(sid: str, body: SessionTitle, request: Request):
    renamed = service(request).store.rename(sid, body.title)
    if not renamed:
        raise HTTPException(404, "会话不存在")
    return renamed


@router.delete("/api/v1/sessions/{sid}")
async def delete_session(sid: str, request: Request):
    if not service(request).store.delete(sid):
        raise HTTPException(404, "会话不存在")
    return Response(status_code=204)


@router.get("/api/v1/sessions/{sid}")
async def get_session(sid: str, request: Request):
    session = service(request).store.session(sid)
    if not session:
        raise HTTPException(404, "会话不存在")
    return session


@router.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    run = service(request).store.run(run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    return run


@router.get("/api/v1/runs/{run_id}/events")
async def events(run_id: str, request: Request, after_event_id: int = -1):
    await get_run(run_id, request)
    return dict(
        run_id=run_id, events=service(request).store.events(run_id, after_event_id)
    )


@router.post("/api/v1/sessions/{sid}/turns")
async def turn(sid: str, body: Message, request: Request):
    await get_session(sid, request)
    query = body.message.strip()
    if not query:
        raise HTTPException(422, "请输入问题")

    async def receive():
        async for event in service(request).stream(sid, body.subject_id, query):
            yield (
                f"event: {event['type']}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(receive(), media_type="text/event-stream")
