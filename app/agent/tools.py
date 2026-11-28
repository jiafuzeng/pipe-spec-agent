"""Agent 工具：规程条款检索。"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextvars import ContextVar

from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from app.agent.utils.compress import compress_items, render_clauses
from app.knowledge.retrieval import search_clauses
from log import trace

_evidence: ContextVar[list | None] = ContextVar("agent_evidence", default=None)
_stream_writer: ContextVar = ContextVar("agent_stream_writer", default=None)


def emit(kind: str, data: dict | None = None, status: str = "running"):
    """经 LangGraph custom stream 推送一条前端事件。

    嵌套 create_agent.astream 会覆盖 Pregel runtime，需先 bind_stream_writer
    固定外层 writer，否则中间 plan_step / tool_call 会丢。
    """
    writer = _stream_writer.get()
    if writer is None:
        try:
            writer = get_stream_writer()
        except Exception:
            return
    try:
        writer(dict(data or {}, type=kind, status=status))
    except Exception:
        return


def bind_stream_writer(writer=None):
    """绑定当前节点的 stream writer，供嵌套 agent / 工具继续 emit。"""
    if writer is None:
        try:
            writer = get_stream_writer()
        except Exception:
            writer = lambda _payload: None
    return _stream_writer.set(writer)


def reset_stream_writer(token) -> None:
    _stream_writer.reset(token)


async def search_evidence(query: str) -> tuple[list, str]:
    """召回条款候选；返回 (items, status)。"""
    try:
        items = (await asyncio.to_thread(search_clauses, query))["evidence"]
        return items, "succeeded"
    except Exception:
        return [], "failed"


@tool("search_clauses")
async def search_clauses_tool(query: str) -> str:
    """检索 CJJ 181—2012 规程条款原文。传入简洁检索 query。"""
    start = time.monotonic()
    items, status = await search_evidence(query)
    emit(
        "tool_call",
        dict(
            tool="search_clauses",
            inputs={"query": query},
            outcome=status,
            call_id=uuid.uuid4().hex,
            elapsed_ms=round(1000 * (time.monotonic() - start)),
            via="in_process",
            summary=(
                f"命中 {len(items)} 条条款候选"
                if items
                else ("检索失败" if status == "failed" else "未命中条款")
            ),
        ),
        status=status if status in {"succeeded", "failed"} else "running",
    )
    bag = _evidence.get()
    if bag is not None:
        bag.extend(items)
    for item in items:
        emit("evidence", item)
    if not items:
        trace("search", query=query, hits=0, status=status)
        return "未命中相关条款原文。"
    raw = sum(len(item.get("quote") or "") for item in items)
    rows = compress_items(items, query)
    body = render_clauses(rows)
    trace(
        "compress",
        query=query,
        hits=len(items),
        raw=raw,
        out=len(body),
        clauses=",".join(row["clause_no"] for row in rows if row.get("clause_no")),
        ms=round(1000 * (time.monotonic() - start)),
    )
    return body


def bind_evidence(bucket: list):
    """把本轮证据列表挂到工具上，返回 reset token。"""
    return _evidence.set(bucket)


def reset_evidence(token) -> None:
    _evidence.reset(token)
