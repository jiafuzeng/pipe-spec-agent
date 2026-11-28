"""Trace 门面：按配置只构造一个 backend。"""

from __future__ import annotations

import logging

from log.backends.langsmith import LangSmithTracer
from log.backends.local import LocalTracer
from log.config import LangSmithConfig, LocalConfig, TraceSettings
from log.context import current_context
from log.events import TraceEvent

_settings: TraceSettings | None = None
_tracer: LocalTracer | LangSmithTracer | None = None


def _configure_app_logger(level_name: str) -> None:
    logger = logging.getLogger("app")
    if logger.handlers:
        return
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.propagate = False


def _build(settings: TraceSettings) -> LocalTracer | LangSmithTracer:
    active = settings.active()
    if isinstance(active, LangSmithConfig):
        return LangSmithTracer(active)
    return LocalTracer(active)


def setup(settings: TraceSettings | None = None):
    """初始化唯一生效的 trace backend。"""
    global _settings, _tracer
    _settings = settings or TraceSettings.from_env()
    _settings.apply_exclusive()
    _configure_app_logger(_settings.local.level)
    _tracer = _build(_settings)
    _tracer.setup()
    return _tracer


def reset() -> None:
    global _settings, _tracer
    _settings = None
    _tracer = None


def get_settings() -> TraceSettings:
    if _settings is None:
        setup()
    assert _settings is not None
    return _settings


def get_tracer() -> LocalTracer | LangSmithTracer:
    if _tracer is None:
        setup()
    assert _tracer is not None
    return _tracer


def chat_callbacks() -> list:
    return get_tracer().chat_callbacks()


def trace(event: str, **fields) -> None:
    ctx = current_context()
    get_tracer().emit(
        TraceEvent(
            event=event,
            fields=fields,
            turn=ctx.get("turn") or "",
            session=ctx.get("session") or "",
            run=ctx.get("run") or "",
        )
    )
