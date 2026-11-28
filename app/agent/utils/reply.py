"""回答事件推送。"""

from __future__ import annotations

import logging

from app.agent.answers import REFUSAL, normalize_citations
from app.agent.tools import emit

log = logging.getLogger(__name__)


def _markdown_body(text: str) -> str:
    return normalize_citations(text) or REFUSAL


def emit_partial_answer(text: str, items: list) -> None:
    """推送流式中间回答（Markdown）。"""
    body = _markdown_body(text)
    emit(
        "answer",
        dict(
            text=body,
            format="markdown",
            citations=[item["evidence_id"] for item in items],
            partial=True,
        ),
    )


def emit_draft_ready(text: str, items: list) -> None:
    """草稿已可阅读：推送完整回答并结束流式光标。"""
    n = len(items)
    body = _markdown_body(text)
    emit(
        "plan_step",
        dict(
            text=(
                "ReAct：草稿已生成"
                + (f"（候选证据 {n} 条）" if n else "（无命中条款）")
            )
        ),
    )
    emit(
        "answer",
        dict(
            text=body,
            format="markdown",
            citations=[item["evidence_id"] for item in items if item.get("evidence_id")],
            partial=False,
        ),
    )
    log.info("draft markdown (%d evidence):\n%s", n, body)


def emit_final_answer(text: str, items: list, *, note: str = "") -> dict:
    """推送最终回答（Markdown），并返回节点状态更新。"""
    n = len(items)
    body = _markdown_body(text)
    log.info("answer markdown (%d evidence):\n%s", n, body)
    step = "回答校验：已定稿" + (f"（依据 {n} 条）" if n else "（无相关依据）")
    if note:
        step = f"{step}；{note}"
    emit("plan_step", dict(text=step))
    emit(
        "answer",
        dict(
            text=body,
            format="markdown",
            citations=[item["evidence_id"] for item in items if item.get("evidence_id")],
            partial=False,
            summary="回答校验",
        ),
        status="completed",
    )
    return dict(evidence=items, draft_answer=body, route="end")
