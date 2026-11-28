"""Trace 配置：local / langsmith 两套接口，运行时只生效一套。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACE_FILE = PROJECT_ROOT / "logs" / "trace.jsonl"

Backend = Literal["local", "langsmith"]
_TRACING_FLAGS = (
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
)


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return default


def resolve_trace_file(raw: str | None = None) -> Path | None:
    """相对路径一律落到项目根；TRACE_FILE=0/off 关闭落盘。"""
    text = (raw if raw is not None else _env("TRACE_FILE")).strip()
    if text.lower() in {"0", "off", "none", "false"}:
        return None
    path = Path(text) if text else DEFAULT_TRACE_FILE
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


@dataclass(frozen=True)
class LocalConfig:
    kind: Literal["local"] = "local"
    level: str = "INFO"
    stream: bool = True
    file: Path | None = None


@dataclass(frozen=True)
class LangSmithConfig:
    kind: Literal["langsmith"] = "langsmith"
    api_key: str = ""
    project: str = "pipe-spec-agent"
    endpoint: str = "https://api.smith.langchain.com"


@dataclass(frozen=True)
class TraceSettings:
    """项目级 trace 设置。`backend` 决定 active() 返回哪一套。"""

    backend: Backend
    local: LocalConfig
    langsmith: LangSmithConfig

    @classmethod
    def from_env(cls) -> TraceSettings:
        load_dotenv()
        backend = (_env("TRACE_BACKEND") or "local").lower()
        if backend not in {"local", "langsmith"}:
            raise ValueError("TRACE_BACKEND 只能是 local 或 langsmith")
        local = LocalConfig(
            level=(_env("TRACE_LEVEL", "LOG_LEVEL") or "INFO").upper(),
            stream=_env("TRACE_STREAM", default="1") != "0",
            file=resolve_trace_file(),
        )
        langsmith = LangSmithConfig(
            api_key=_env("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
            project=_env("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT") or "pipe-spec-agent",
            endpoint=_env(
                "LANGSMITH_ENDPOINT",
                "LANGCHAIN_ENDPOINT",
                default="https://api.smith.langchain.com",
            ),
        )
        settings = cls(backend=backend, local=local, langsmith=langsmith)
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.backend == "langsmith" and not self.langsmith.api_key:
            raise ValueError("TRACE_BACKEND=langsmith 时需要 LANGSMITH_API_KEY")

    def active(self) -> LocalConfig | LangSmithConfig:
        return self.langsmith if self.backend == "langsmith" else self.local

    def apply_exclusive(self) -> None:
        """只让当前 backend 的 tracing 开关生效，避免两套同时上报。"""
        if self.backend == "langsmith":
            cfg = self.langsmith
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = cfg.api_key
            os.environ["LANGSMITH_API_KEY"] = cfg.api_key
            os.environ["LANGCHAIN_PROJECT"] = cfg.project
            os.environ["LANGSMITH_PROJECT"] = cfg.project
            os.environ["LANGCHAIN_ENDPOINT"] = cfg.endpoint
            os.environ["LANGSMITH_ENDPOINT"] = cfg.endpoint
            return
        for key in _TRACING_FLAGS:
            os.environ[key] = "false"
