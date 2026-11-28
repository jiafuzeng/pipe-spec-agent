"""ChatOpenAI 回调：把模型起止/失败写成结构化 trace 事件。"""

from __future__ import annotations

import time

from langchain_core.callbacks import BaseCallbackHandler

_started: dict[str, float] = {}


def _message_chars(messages) -> int:
    total = 0
    for group in messages or []:
        rows = group if isinstance(group, (list, tuple)) else [group]
        for msg in rows:
            content = getattr(msg, "content", msg)
            total += len(content) if isinstance(content, str) else len(str(content))
    return total


class ChatTraceCallback(BaseCallbackHandler):
    """仅本地 backend 使用；LangSmith 走 LangChainTracer，避免双写。"""

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        from log import trace

        key = str(run_id)
        _started[key] = time.monotonic()
        trace("llm.start", chars=_message_chars(messages))

    def on_llm_end(self, response, *, run_id, **kwargs):
        from log import trace

        key = str(run_id)
        start = _started.pop(key, None)
        ms = round(1000 * (time.monotonic() - start)) if start is not None else None
        gens = getattr(response, "generations", None) or []
        out = 0
        for row in gens:
            for gen in row:
                text = getattr(gen, "text", None) or str(getattr(gen, "message", "") or "")
                out += len(text)
        trace("llm.end", ms=ms, out=out)

    def on_llm_error(self, error, *, run_id, **kwargs):
        from log import trace

        key = str(run_id)
        start = _started.pop(key, None)
        ms = round(1000 * (time.monotonic() - start)) if start is not None else None
        trace("llm.error", ms=ms, error=type(error).__name__)
