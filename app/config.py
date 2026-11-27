"""Server-side connection settings. Secrets stay out of UI payloads and logs."""

import os


def mcp_url():
    return os.getenv("MCP_URL", "http://127.0.0.1:8001/mcp").rstrip("/")


def mcp_headers():
    token = os.getenv("MCP_TOKEN")
    return {"Authorization": "Bearer " + token} if token else {}


def mcp_timeout():
    return float(os.getenv("MCP_TIMEOUT_SECONDS", "45"))
