"""问答入口：session_id = LangGraph thread_id。"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.agent.graph import get_graph

router = APIRouter()
log = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Store 未就绪")
    return store


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    subject_id: str = Field(default="default", min_length=1, max_length=128)


class SessionTitle(BaseModel):
    title: str = Field(min_length=1, max_length=80)


@router.post("/api/v1/sessions")
async def create_session(request: Request):
    sid, created = uuid.uuid4().hex, _now()
    await _store(request).aput(
        ("sessions",),
        sid,
        {"created_at": created, "title": None, "last_message": None},
    )
    return dict(session_id=sid, created_at=created, state="ready")


@router.get("/api/v1/sessions")
async def list_sessions(request: Request):
    rows = []
    for item in await _store(request).asearch(("sessions",), limit=1000):
        value = item.value or {}
        if not value.get("last_message"):
            continue
        rows.append(
            dict(
                session_id=item.key,
                title=value.get("title"),
                last_message=value["last_message"],
                last_activity_at=value.get("last_activity_at") or value.get("created_at"),
            )
        )
    rows.sort(key=lambda row: row["last_activity_at"] or "", reverse=True)
    return rows


@router.get("/api/v1/sessions/{sid}")
async def get_session(sid: str, request: Request):
    store = _store(request)
    item = await store.aget(("sessions",), sid)
    if item is None:
        raise HTTPException(404, "会话不存在")
    turns = sorted(
        await store.asearch(("turns", sid), limit=10000),
        key=lambda row: (row.value or {}).get("created_at") or row.key,
    )
    messages = [
        dict(
            turn_id=t.key,
            run_id=(t.value or {}).get("run"),
            subject_id=(t.value or {}).get("subject") or "default",
            text=(t.value or {}).get("message") or "",
            role="user",
        )
        for t in turns
    ]
    last = messages[-1] if messages else None
    return dict(
        session_id=sid,
        created_at=(item.value or {}).get("created_at"),
        state="ready",
        messages=messages,
        active_run_id=last["run_id"] if last else None,
        subject_id=last["subject_id"] if last else "default",
    )


@router.patch("/api/v1/sessions/{sid}")
async def rename_session(sid: str, body: SessionTitle, request: Request):
    store = _store(request)
    item = await store.aget(("sessions",), sid)
    if item is None:
        raise HTTPException(404, "会话不存在")
    value = dict(item.value or {}, title=body.title.strip())
    await store.aput(("sessions",), sid, value)
    return dict(session_id=sid, title=value["title"])


@router.delete("/api/v1/sessions/{sid}")
async def delete_session(sid: str, request: Request):
    store = _store(request)
    if await store.aget(("sessions",), sid) is None:
        raise HTTPException(404, "会话不存在")
    for turn in await store.asearch(("turns", sid), limit=10000):
        run = (turn.value or {}).get("run")
        if run:
            for event in await store.asearch(("events", run), limit=10000):
                await store.adelete(("events", run), event.key)
            await store.adelete(("runs",), run)
        await store.adelete(("turns", sid), turn.key)
    await store.adelete(("sessions",), sid)
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is not None:
        await checkpointer.adelete_thread(sid)
    return Response(status_code=204)


@router.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    item = await _store(request).aget(("runs",), run_id)
    if item is None:
        raise HTTPException(404, "run 不存在")
    info = item.value or {}
    return dict(
        run_id=run_id,
        session_id=info.get("sid"),
        subject_id=info.get("subject"),
        status=info.get("status"),
        event_count=int(info.get("event_seq") or -1) + 1,
    )


@router.get("/api/v1/runs/{run_id}/events")
async def list_events(run_id: str, request: Request, after_event_id: int = -1):
    await get_run(run_id, request)
    rows = sorted(
        await _store(request).asearch(("events", run_id), limit=10000),
        key=lambda item: item.key,
    )
    return dict(
        run_id=run_id,
        events=[
            item.value
            for item in rows
            if int((item.value or {}).get("event_id", -1)) > after_event_id
        ],
    )


@router.post("/api/v1/sessions/{sid}/turns")
async def turn(sid: str, body: Message, request: Request):
    store = _store(request)
    if await store.aget(("sessions",), sid) is None:
        raise HTTPException(404, "会话不存在")
    query = body.message.strip()
    if not query:
        raise HTTPException(422, "请输入问题")

    run_id, turn_id, created = uuid.uuid4().hex, uuid.uuid4().hex, _now()
    await store.aput(
        ("runs",),
        run_id,
        {
            "sid": sid,
            "subject": body.subject_id,
            "status": "running",
            "event_seq": -1,
        },
    )
    await store.aput(
        ("turns", sid),
        turn_id,
        {
            "run": run_id,
            "message": query,
            "created_at": created,
            "subject": body.subject_id,
        },
    )
    session = await store.aget(("sessions",), sid)
    meta = dict(session.value or {})
    meta.update(last_message=query, last_activity_at=created)
    await store.aput(("sessions",), sid, meta)

    graph = get_graph()
    if graph is None:
        raise HTTPException(503, "图未就绪")

    async def receive():
        seq = -1
        try:
            stream = graph.astream(
                {"query": query},
                {"configurable": {"thread_id": sid}},
                stream_mode="custom",
            )
            async for chunk in stream:
                if not isinstance(chunk, dict) or not chunk.get("type"):
                    continue
                seq += 1
                status = chunk.get("status") or "running"
                data = {
                    k: v for k, v in chunk.items() if k not in {"type", "status"}
                }
                event = dict(
                    data,
                    type=chunk["type"],
                    run_id=run_id,
                    turn_id=turn_id,
                    event_id=seq,
                    session_id=sid,
                    subject_id=body.subject_id,
                    step_id=f"{turn_id}-{seq}",
                )
                await store.aput(("events", run_id), f"{seq:08d}", event)
                await store.aput(
                    ("runs",),
                    run_id,
                    {
                        "sid": sid,
                        "subject": body.subject_id,
                        "status": status,
                        "event_seq": seq,
                    },
                )
                yield (
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
        except Exception:
            log.exception("turn %s failed", turn_id)
            seq += 1
            event = dict(
                type="error",
                code="TOOL_UNAVAILABLE",
                text="执行中断，可重新提交。",
                retryable=True,
                run_id=run_id,
                turn_id=turn_id,
                event_id=seq,
                session_id=sid,
            )
            await store.aput(("events", run_id), f"{seq:08d}", event)
            await store.aput(
                ("runs",),
                run_id,
                {
                    "sid": sid,
                    "subject": body.subject_id,
                    "status": "failed",
                    "event_seq": seq,
                },
            )
            yield (
                f"event: error\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(receive(), media_type="text/event-stream")
