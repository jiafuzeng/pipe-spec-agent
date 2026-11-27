"""意图识别 + LangChain create_agent 检索。"""

import asyncio
import json
import time
import uuid
from typing import Required, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.agent.answers import (
    REFUSAL,
    classify_turn,
    grounded_summary,
    normalize_citations,
)
from app.agent.language import IntentResult, chat_model, structured
from app.knowledge.retrieval import search_clauses
from app.settings import chat

_REACT_MAX_STEPS = 4
_CHITCHAT_REPLY = (
    "我是排水管道规程助手，可问 CJJ 181—2012 条款、适用条件或检测方案。"
)
_AGENT_PROMPT = (
    "你是排水管道规程助手，只依据 CJJ 181—2012 原文回答。"
    "缺依据时调用 search_clauses；有足够条款后再总结。不编造条款号与原文。"
)


class State(TypedDict, total=False):
    """图状态：问题、意图与证据。"""

    query: Required[str]
    intent: str
    evidence: list
    route: str


def emit(kind: str, data: dict | None = None, status: str = "running"):
    """经 LangGraph custom stream 推送一条前端事件。"""
    get_stream_writer()(dict(data or {}, type=kind, status=status))


async def _search(query: str) -> tuple[list, str]:
    """召回条款候选；返回 (items, status)。"""
    try:
        items = (await asyncio.to_thread(search_clauses, query))["evidence"]
        return items, "succeeded"
    except Exception:
        return [], "failed"


def _last_ai_text(messages) -> str:
    """取最后一条无 tool_calls 的 AI 文本。"""
    for message in reversed(messages or []):
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        text = message.content if isinstance(message.content, str) else str(message.content or "")
        if text.strip():
            return text
    return ""


def _answer(text: str, items: list):
    """推送最终回答事件，并返回节点状态更新。"""
    emit("plan_step", dict(text="ReAct：检索总结"))
    emit(
        "answer",
        dict(
            text=normalize_citations(text) or REFUSAL,
            citations=[item["evidence_id"] for item in items],
            partial=False,
        ),
        status="completed",
    )
    return dict(evidence=items, route="end")


async def recognize(state: State):
    """先规则判意图；仅规则落成 qa 时再用 LLM。"""
    q = state["query"]
    intent = classify_turn(q)
    if intent == "qa":
        proposal = await structured(
            IntentResult,
            "只判定意图：qa/compare/explain/plan/chitchat。"
            "寒暄、身份介绍标为 chitchat。",
            {"问题": q},
        )
        if proposal and proposal.intent:
            intent = proposal.intent
    emit("plan_step", dict(text=f"意图识别：{intent}", intent=intent))
    if intent == "chitchat":
        emit(
            "answer",
            dict(text=_CHITCHAT_REPLY, citations=[], partial=False),
            status="completed",
        )
        return dict(intent=intent, query=q, route="end")

    emit("plan_step", dict(text="进入 ReAct 检索", questions=[q], intent=intent))
    return dict(intent=intent, query=q, evidence=[], route="react")


async def react(state: State):
    """create_agent 检索循环；模型不可用则单次检索。"""
    q = state["query"]
    intent = state.get("intent") or "qa"
    collected: list[dict] = []

    @tool("search_clauses")
    async def search_clauses_tool(query: str) -> str:
        """检索 CJJ 181—2012 规程条款原文。传入简洁检索 query。"""
        start = time.monotonic()
        items, status = await _search(query)
        emit(
            "tool_call",
            dict(
                tool="search_clauses",
                inputs={"query": query},
                status=status,
                call_id=uuid.uuid4().hex,
                elapsed_ms=round(1000 * (time.monotonic() - start)),
                via="in_process",
                summary=f"{len(items)} 条候选",
            ),
        )
        collected.extend(items)
        for item in items:
            emit("evidence", item)
        if not items:
            return "未命中相关条款原文。"
        return json.dumps(
            [{"clause_no": i["clause_no"], "quote": i["quote"][:240]} for i in items],
            ensure_ascii=False,
        )

    if not chat().ready:
        items, _ = await _search(q)
        for item in items:
            emit("evidence", item)
        return _answer(grounded_summary(items) or REFUSAL, items)

    emit("plan_step", dict(text="ReAct：create_agent", intent=intent))
    agent = create_agent(
        model=chat_model(),
        tools=[search_clauses_tool],
        system_prompt=f"{_AGENT_PROMPT}当前意图：{intent}。",
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": q}]},
        {"recursion_limit": _REACT_MAX_STEPS * 2 + 2},
    )
    text = _last_ai_text(result.get("messages")) or grounded_summary(collected) or REFUSAL
    return _answer(text, collected)


def _route(state: State) -> str:
    return state.get("route") or "end"


def compile_graph(checkpointer=None, store=None):
    """编译 recognize → react（create_agent）图。"""
    g = StateGraph(State)
    g.add_node("recognize", recognize)
    g.add_node("react", react)
    g.add_edge(START, "recognize")
    g.add_conditional_edges("recognize", _route, {"react": "react", "end": END})
    g.add_edge("react", END)
    return g.compile(checkpointer=checkpointer, store=store)


workflow = compile_graph()
_graph = None


def get_graph():
    return _graph or workflow


def set_graph(compiled):
    global _graph
    _graph = compiled
