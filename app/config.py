"""Server-side connection settings. Secrets stay out of UI payloads and logs."""

import os
from pathlib import Path


def mcp_url():
    return os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp").rstrip("/")


def mcp_headers():
    token = os.getenv("MCP_TOKEN")
    return {"Authorization": "Bearer " + token} if token else {}


def mcp_timeout():
    return float(os.getenv("MCP_TIMEOUT_SECONDS", "45"))


def langgraph_db():
    return os.getenv("LANGGRAPH_DB", "data/agent/langgraph.sqlite")


def langgraph_path(business_db=None):
    chosen = os.getenv("LANGGRAPH_DB")
    if chosen:
        return Path(chosen)
    if business_db is not None:
        return Path(business_db).with_name("langgraph.sqlite")
    return Path(langgraph_db())
