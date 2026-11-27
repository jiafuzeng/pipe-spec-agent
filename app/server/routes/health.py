import os
from fastapi import APIRouter
from app.server.routes import knowledge
from app.config import mcp_headers, mcp_url

router = APIRouter()


@router.get("/health")
def healthcheck():
    components = {
        "app": {"status": "ok"},
        "registry": {"status": "ok"},
        "embedding": {
            "status": "configured"
            if os.getenv("OLLAMA_BASE_URL") or os.getenv("DASHSCOPE_API_KEY")
            else "unconfigured"
        },
        "chat_model": {
            "status": "configured" if os.getenv("CHAT_BASE_URL") else "unconfigured"
        },
        "reranker": {
            "status": "configured"
            if os.getenv("RERANKER_BASE_URL") or os.getenv("RERANKER_MODEL")
            else "unconfigured"
        },
        "mcp": {"status": "unavailable"},
    }
    try:
        with knowledge.db.connect() as connection:
            connection.execute("SELECT 1")
    except Exception as exc:
        components["registry"] = {"status": "error", "detail": str(exc)}
    import httpx

    try:
        response = httpx.get(
            mcp_url().removesuffix("/mcp") + "/health",
            headers=mcp_headers(),
            timeout=1.5,
        )
        if response.is_success and response.json().get("status") == "ok":
            components["mcp"] = {"status": "ok"}
    except (ValueError, httpx.HTTPError):
        pass
    return {"status": "ok", "components": components}
