"""结构化 trace 事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value).replace("\n", " ").strip()
    if len(text) > 200:
        return text[:199] + "…"
    return text


@dataclass
class TraceEvent:
    event: str
    fields: dict[str, Any] = field(default_factory=dict)
    turn: str = ""
    session: str = ""
    run: str = ""
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    )

    def payload(self) -> dict[str, Any]:
        data: dict[str, Any] = {"event": self.event, "ts": self.ts}
        if self.turn:
            data["turn"] = self.turn[:8] if len(self.turn) > 8 else self.turn
        if self.session:
            data["session"] = self.session[:8]
        if self.run:
            data["run"] = self.run[:8]
        for key, value in self.fields.items():
            if value is None or key in data:
                continue
            data[key] = _jsonable(value)
        return data
