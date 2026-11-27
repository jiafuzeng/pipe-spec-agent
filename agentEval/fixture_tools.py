"""In-process calculation adapter for contract tests only."""


async def call_tool(name: str, args: dict):
    import os

    if os.getenv("MCP_URL") == "offline":
        raise ConnectionError("MCP offline")
    from pipe_assessment_mcp import server as mcp

    fn = {
        "get_calculation_schema": mcp.get_calculation_schema,
        "lookup_defect_score": mcp.lookup_defect_score,
        "calculate_index": mcp.calculate_index,
        "plot_curve": mcp.plot_curve,
    }.get(name)
    if not fn:
        raise RuntimeError(f"未知工具 {name}")
    return fn(**args)
