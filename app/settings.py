"""全局应用配置（模块级变量，进程启动时从环境 / .env 加载）。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

AGENT_MODEL_ENABLED = os.getenv("AGENT_MODEL_ENABLED", "1") != "0"
CHAT_MODEL = (os.getenv("CHAT_MODEL") or "").strip()
CHAT_BASE_URL = (os.getenv("CHAT_BASE_URL") or "").rstrip("/")
CHAT_API_KEY = os.getenv("CHAT_API_KEY") or "EMPTY"
CHAT_TIMEOUT = float(os.getenv("CHAT_TIMEOUT_SECONDS", "15"))
CHAT_READY = AGENT_MODEL_ENABLED and bool(CHAT_MODEL) and bool(CHAT_BASE_URL)

AGENT_DB = Path(os.getenv("AGENT_DB", "data/agent/journal.sqlite"))
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
)

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp").rstrip("/")
MCP_TOKEN = os.getenv("MCP_TOKEN") or None
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT_SECONDS", "45"))
MCP_HEADERS = (
    {"Authorization": "Bearer " + MCP_TOKEN} if MCP_TOKEN else {}
)

LANGGRAPH_DB = Path(os.getenv("LANGGRAPH_DB", "data/agent/langgraph.sqlite"))
