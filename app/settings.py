"""统一从环境变量 / .env 加载应用配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_loaded = False


def load() -> None:
    """幂等加载 .env，供各模块在读环境变量前调用。"""
    global _loaded
    if _loaded:
        return
    load_dotenv()
    _loaded = True


@dataclass(frozen=True)
class ChatSettings:
    """OpenAI 兼容聊天模型配置（CHAT_* / AGENT_MODEL_ENABLED）。"""

    enabled: bool
    model: str
    base_url: str
    api_key: str
    timeout: float = 15.0

    @property
    def ready(self) -> bool:
        """是否允许发起模型调用。"""
        return self.enabled and bool(self.model) and bool(self.base_url)


def chat() -> ChatSettings:
    """读取当前聊天模型配置。"""
    load()
    return ChatSettings(
        enabled=os.getenv("AGENT_MODEL_ENABLED", "1") != "0",
        model=(os.getenv("CHAT_MODEL") or "").strip(),
        base_url=(os.getenv("CHAT_BASE_URL") or "").rstrip("/"),
        api_key=os.getenv("CHAT_API_KEY") or "EMPTY",
        timeout=float(os.getenv("CHAT_TIMEOUT_SECONDS", "15")),
    )


def agent_db() -> Path:
    """会话/事件库路径。"""
    load()
    return Path(os.getenv("AGENT_DB", "data/agent/journal.sqlite"))


def cors_origins() -> list[str]:
    """前端 CORS 允许来源。"""
    load()
    return [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",")
        if origin.strip()
    ]


def mcp_url() -> str:
    load()
    return os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp").rstrip("/")


def mcp_headers() -> dict[str, str]:
    load()
    token = os.getenv("MCP_TOKEN")
    return {"Authorization": "Bearer " + token} if token else {}


def mcp_timeout() -> float:
    load()
    return float(os.getenv("MCP_TIMEOUT_SECONDS", "45"))


def langgraph_db() -> str:
    load()
    return os.getenv("LANGGRAPH_DB", "data/agent/langgraph.sqlite")


def langgraph_path(business_db=None) -> Path:
    """LangGraph checkpointer / store 的 SQLite 路径。"""
    load()
    chosen = os.getenv("LANGGRAPH_DB")
    if chosen:
        return Path(chosen)
    if business_db is not None:
        return Path(business_db).with_name("langgraph.sqlite")
    return Path(langgraph_db())
