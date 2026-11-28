"""Trace backend 接口。"""

from __future__ import annotations

from typing import Protocol

from log.events import TraceEvent


class Tracer(Protocol):
    def setup(self) -> None: ...
    def emit(self, event: TraceEvent) -> None: ...
    def chat_callbacks(self) -> list: ...
