"""create_agent 构建。"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app import settings
from app.agent.prompts import AGENT_PROMPT, REACT_MAX_STEPS
from app.agent.tools import search_clauses_tool


def build_search_agent(*, intent: str, label: str, search_query: str):
    """构建规程检索用 create_agent。"""
    return create_agent(
        model=ChatOpenAI(
            model=settings.CHAT_MODEL,
            api_key=SecretStr(settings.CHAT_API_KEY),
            base_url=settings.CHAT_BASE_URL,
            temperature=0,
            timeout=settings.CHAT_TIMEOUT,
        ),
        tools=[search_clauses_tool],
        system_prompt=(
            f"{AGENT_PROMPT}\n"
            f"当前意图：{label}（{intent}）。优先用改写查询检索：{search_query}。"
        ),
    )


def react_recursion_limit() -> int:
    return REACT_MAX_STEPS * 2 + 2
