"""消息解析。"""

from langchain_core.messages import AIMessage


def last_ai_text(messages) -> str:
    """取最后一条无 tool_calls 的 AI 文本。"""
    for message in reversed(messages or []):
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        text = (
            message.content
            if isinstance(message.content, str)
            else str(message.content or "")
        )
        if text.strip():
            return text
    return ""
