import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from langchain_core.messages import HumanMessage
from langchain_core.tracers.langchain import LangChainTracer

from log import (
    LangSmithConfig,
    LocalConfig,
    TraceSettings,
    bind_turn,
    chat_callbacks,
    reset,
    reset_turn,
    setup,
    trace,
)
from log.backends.langsmith import LangSmithTracer
from log.callbacks import ChatTraceCallback
from log import tracer as facade


class _FakeLangSmith:
    def __init__(self):
        self.runs = []

    def create_run(self, **kwargs):
        self.runs.append(kwargs)


def _payload(line: str) -> dict:
    return json.loads(line.split(":", 2)[2])


class TraceTests(unittest.TestCase):
    def tearDown(self):
        reset()

    def test_default_backend_is_local_only(self):
        with patch.dict(
            os.environ,
            {"TRACE_BACKEND": "local", "LANGCHAIN_TRACING_V2": "true"},
        ):
            settings = TraceSettings.from_env()
            self.assertEqual(settings.backend, "local")
            self.assertEqual(settings.active().kind, "local")
            settings.apply_exclusive()
            self.assertEqual(os.environ.get("LANGCHAIN_TRACING_V2"), "false")
            self.assertEqual(os.environ.get("LANGSMITH_TRACING"), "false")

    def test_langsmith_backend_requires_key(self):
        with patch.dict(
            os.environ,
            {
                "TRACE_BACKEND": "langsmith",
                "LANGSMITH_API_KEY": "",
                "LANGCHAIN_API_KEY": "",
            },
        ):
            with self.assertRaises(ValueError):
                TraceSettings.from_env()

    def test_local_emits_json_with_turn(self):
        setup(
            TraceSettings(
                backend="local", local=LocalConfig(), langsmith=LangSmithConfig()
            )
        )
        token = bind_turn("abcd1234ffff", session="sess", run="runid")
        try:
            with self.assertLogs("trace", level="INFO") as captured:
                trace("compress", raw=8000, out=300, clauses="3.0.4")
        finally:
            reset_turn(token)
        payload = _payload(captured.output[0])
        self.assertEqual(payload["event"], "compress")
        self.assertEqual(payload["turn"], "abcd1234")
        self.assertEqual(payload["out"], 300)
        self.assertEqual(payload["clauses"], "3.0.4")

    def test_local_chat_callback(self):
        setup(
            TraceSettings(
                backend="local", local=LocalConfig(), langsmith=LangSmithConfig()
            )
        )
        self.assertIsInstance(chat_callbacks()[0], ChatTraceCallback)
        with self.assertLogs("trace", level="INFO") as captured:
            cb = chat_callbacks()[0]
            cb.on_chat_model_start(
                {}, [[HumanMessage(content="hello")]], run_id="run-1"
            )
            cb.on_llm_error(TimeoutError("Request timed out."), run_id="run-1")
        text = "\n".join(captured.output)
        self.assertIn('"event": "llm.start"', text)
        self.assertIn('"event": "llm.error"', text)
        self.assertIn("TimeoutError", text)

    def test_langsmith_is_exclusive_and_uses_client(self):
        fake = _FakeLangSmith()
        settings = TraceSettings(
            backend="langsmith",
            local=LocalConfig(),
            langsmith=LangSmithConfig(api_key="sk-test", project="pipe-spec"),
        )
        tracer = LangSmithTracer(settings.langsmith, client=fake)
        with patch.dict(os.environ, {"LANGCHAIN_TRACING_V2": "false"}):
            settings.apply_exclusive()
            self.assertEqual(os.environ.get("LANGCHAIN_TRACING_V2"), "true")
            self.assertEqual(os.environ.get("LANGSMITH_PROJECT"), "pipe-spec")
            facade._settings = settings
            facade._tracer = tracer
            token = bind_turn("turn-1")
            try:
                trace("compress", raw=12, clauses="3.0.4")
            finally:
                reset_turn(token)
        self.assertEqual(len(fake.runs), 1)
        self.assertEqual(fake.runs[0]["name"], "compress")
        self.assertEqual(fake.runs[0]["project_name"], "pipe-spec")
        cb = tracer.chat_callbacks()[0]
        self.assertIsInstance(cb, LangChainTracer)
        self.assertNotIsInstance(cb, ChatTraceCallback)

    def test_local_writes_project_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            setup(
                TraceSettings(
                    backend="local",
                    local=LocalConfig(stream=False, file=path),
                    langsmith=LangSmithConfig(),
                )
            )
            self.assertTrue(path.is_file())
            trace("compress", raw=1, out=1)
            text = path.read_text(encoding="utf-8")
            self.assertIn('"event": "trace.ready"', text)
            self.assertIn('"event": "compress"', text)
