import asyncio
from app.config import mcp_url, mcp_headers, mcp_timeout
import json


async def call_tool(name, args):
    """Invoke the separately deployed Streamable HTTP service."""
    url = mcp_url()
    if url == "offline":
        raise ConnectionError("MCP offline")

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import httpx

    async with (
        asyncio.timeout(mcp_timeout()),
        httpx.AsyncClient(headers=mcp_headers(), timeout=mcp_timeout()) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            if result.isError:
                raise RuntimeError("工具执行失败")
            return result.structuredContent or json.loads(result.content[0].text)


async def fetch_artifact(resource_id):
    import httpx
    from fastapi import HTTPException

    url = mcp_url()
    base = url.rstrip("/").removesuffix("/mcp")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                base + "/artifacts/" + resource_id, headers=mcp_headers()
            )
            if response.status_code == 404:
                raise HTTPException(404, "资源不存在")
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        raise HTTPException(503, "图表服务不可用") from exc
