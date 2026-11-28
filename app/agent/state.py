"""LangGraph 图状态。"""

from typing import Required, TypedDict

from app.agent.language import Intent


class State(TypedDict, total=False):
    """图状态：原问、改写检索问、草稿回答、意图与证据。"""

    query: Required[str]
    search_query: str
    intent: Intent
    draft_answer: str
    evidence: list
    route: str


def route(state: State) -> str:
    """条件边：按 state.route 跳转，缺省结束。"""
    return state.get("route") or "end"
