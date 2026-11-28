"""create_agent 执行进度 → plan_step。"""

from langchain_core.messages import AIMessage

from app.agent.tools import emit
from app.agent.utils.messages import last_ai_text


def tool_call_label(call) -> str:
    """格式化 tool_call 为 name「query」。"""
    data = call if isinstance(call, dict) else {
        "name": getattr(call, "name", None),
        "args": getattr(call, "args", None),
    }
    name = data.get("name") or "tool"
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    query = str(args.get("query") or "").strip()
    return f"{name}「{query}」" if query else name


def emit_agent_progress(update: dict) -> None:
    """把 create_agent 单步 updates 转成前端可展示的 plan_step。"""
    for node, payload in update.items():
        if node == "model":
            messages = (payload or {}).get("messages") or []
            last = messages[-1] if messages else None
            if isinstance(last, AIMessage) and last.tool_calls:
                labels = ", ".join(tool_call_label(c) for c in last.tool_calls)
                emit(
                    "plan_step",
                    dict(text=f"ReAct：模型决定调用工具 {labels}"),
                )
            elif isinstance(last, AIMessage) and last_ai_text([last]):
                emit(
                    "plan_step",
                    dict(text="ReAct：模型依据检索结果整理回答"),
                )
        elif node == "tools":
            emit(
                "plan_step",
                dict(text="ReAct：工具结果已回传，准备继续推理"),
            )
