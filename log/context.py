"""当前 turn / session / run，供各 backend 共用。"""

from __future__ import annotations

from contextvars import ContextVar, Token

_ctx: ContextVar[dict[str, str]] = ContextVar("trace_ctx", default={})


def bind_turn(turn_id: str, *, session: str = "", run: str = "") -> Token:
    current = dict(_ctx.get() or {})
    current.update(turn=turn_id or "", session=session or "", run=run or "")
    return _ctx.set(current)


def reset_turn(token: Token) -> None:
    _ctx.reset(token)


def current_context() -> dict[str, str]:
    return dict(_ctx.get() or {})
