import asyncio
import json
import re
import uuid
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.agent.store import Store
from app.agent.workflow import Turn, workflow
from app.integrations.mcp_client import fetch_artifact

router = APIRouter()


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    subject_id: str = Field(default="default", min_length=1, max_length=128)


def resumes_task(state, query):
    pending = state.get("pending")
    if not pending:
        return False
    if pending == "plan":
        return bool(
            re.search(
                r"管径|DN\s*\d|水位|流速|管段长度|管长|探头|竣工资料", query, re.I
            )
            and not re.search(r"计算|对比|比较|另外一段", query)
        )
    return bool(
        re.search(r"[A-Za-z]+\s*[=:：]|继续|重试|[FKET]\s*(为|是)", query)
        or (state.get("observations") and re.search("土质|确认|米|间距", query))
        or any(
            f.get("label_zh") and f["label_zh"] in query
            for f in state.get("missing", [])
        )
    )


class Execution:
    def __init__(self, store, tool_client=None):
        self.tool_client = tool_client
        self.store = store
        self.locks = WeakValueDictionary()
        self.tasks = set()

    def submit(self, sid, subject, query, recovering=None):
        queue = asyncio.Queue()
        lock = self.locks.setdefault((sid, subject), asyncio.Lock())

        async def run():
            async with lock:
                try:
                    state, version = self.store.subject(sid, subject)
                    if recovering:
                        run_id, turn_id = recovering["run"], recovering["turn"]
                    else:
                        continuing = resumes_task(state, query)
                        run_id = state["run"] if continuing else uuid.uuid4().hex
                        turn_id = uuid.uuid4().hex
                        if not continuing:
                            state.update(
                                pending=None,
                                rule_version=None,
                                curve=None,
                                missing=[],
                                compare_base=False,
                            )
                        state.update(run=run_id, continuing=continuing)
                        self.store.start(
                            sid, subject, run_id, turn_id, query, state, version
                        )
                        version += 1
                    ctx = Turn(
                        self.store,
                        run_id,
                        turn_id,
                        state,
                        version,
                        queue,
                        self.tool_client,
                    )
                    try:
                        initial = self.store.restore(turn_id) if recovering else None
                        await workflow.ainvoke(initial or {"query": query}, context=ctx)
                    except Exception:
                        import logging

                        logging.getLogger(__name__).exception("Turn %s failed", turn_id)
                        ctx.emit(
                            "error",
                            dict(
                                code="TOOL_UNAVAILABLE",
                                text="执行中断，可重新提交。",
                                retryable=True,
                            ),
                            "failed",
                        )
                finally:
                    queue.put_nowait(None)

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return queue


def service(request):
    if not hasattr(request.app.state, "execution"):
        request.app.state.execution = Execution(Store())
    return request.app.state.execution


@router.post("/api/v1/sessions")
async def create_session(request: Request):
    return service(request).store.create()


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


@router.get("/api/v1/artifacts/{resource_id}")
async def artifact(resource_id: str):
    if not re.fullmatch(r"[0-9a-f]{64}", resource_id):
        raise HTTPException(404, "资源不存在")
    content = await fetch_artifact(resource_id)
    return Response(content, media_type="image/png")


@router.post("/api/v1/sessions/{sid}/turns")
async def turn(sid: str, body: Message, request: Request):
    await get_session(sid, request)
    query = body.message.strip()
    if not query:
        raise HTTPException(422, "请输入问题")
    queue = service(request).submit(sid, body.subject_id, query)

    async def receive():
        while (event := await queue.get()) is not None:
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(receive(), media_type="text/event-stream")
