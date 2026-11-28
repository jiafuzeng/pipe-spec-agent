"""LangSmith 接口：自定义事件走 Client.create_run，模型调用走 LangChainTracer。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from log.config import LangSmithConfig
from log.events import TraceEvent

log = logging.getLogger("log.langsmith")


class LangSmithTracer:
    def __init__(self, config: LangSmithConfig, client=None):
        self._config = config
        self._client = client

    def setup(self) -> None:
        if self._client is not None:
            return
        from langsmith import Client

        self._client = Client(
            api_key=self._config.api_key,
            api_url=self._config.endpoint,
        )

    def emit(self, event: TraceEvent) -> None:
        if self._client is None:
            self.setup()
        now = datetime.now(timezone.utc)
        payload = event.payload()
        name = payload.pop("event")
        try:
            self._client.create_run(
                id=uuid4(),
                name=name,
                run_type="chain",
                inputs=payload,
                outputs={"ok": True},
                project_name=self._config.project,
                start_time=now,
                end_time=now,
                extra={"metadata": {"turn": event.turn, "session": event.session}},
            )
        except Exception:
            log.exception("langsmith emit failed: %s", name)

    def chat_callbacks(self) -> list:
        from langchain_core.tracers.langchain import LangChainTracer

        if self._client is None:
            self.setup()
        return [
            LangChainTracer(
                client=self._client,
                project_name=self._config.project,
            )
        ]
