"""LLM 意图识别与检索问题改写。"""

from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from app import settings
from app.agent.prompts import INTENT_LABEL, INTENT_PROMPT
from log import chat_callbacks, trace

# 全局意图（规则初判 + LLM 共用）
# retrieve  基础条文与概念检索 → ReAct
# compare   检测方法与方案对比 → ReAct
# compute   计算推理、智能问数与可视化 → ReAct
# chitchat  闲聊 → 直答，不检索
Intent = Literal["retrieve", "compare", "compute", "chitchat"]


_REWRITE_INSTRUCTION = """你是排水管道规程（CJJ 181—2012）检索查询改写器。
根据用户问题与意图，改写成适合条款检索的简洁中文查询。

要求：
<ul>
<li>保留检测方法、管径、水位、条款主题、计算对象等关键实体</li>
<li>去掉寒暄、口语赘词与无关背景</li>
<li>retrieve：突出要查的条文主题或概念</li>
<li>compare：突出需对照的检测方法、方案或现场选用条件</li>
<li>compute：突出计算对象、指标或要统计/可视化的量</li>
<li>只输出一条检索查询，不要解释</li>
</ul>"""


class IntentResult(BaseModel):
    """LLM 意图判定输出。"""

    intent: Intent
    reason: str = Field(default="", description="一句话说明为何选该类")


class RewriteResult(BaseModel):
    """检索用改写查询。"""

    query: str = Field(min_length=1, description="改写后的检索查询")


def _chat() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.CHAT_MODEL,
        api_key=SecretStr(settings.CHAT_API_KEY),
        base_url=settings.CHAT_BASE_URL,
        temperature=0,
        timeout=settings.CHAT_TIMEOUT,
        max_retries=0,
        callbacks=chat_callbacks(),
    )


async def recognize_intent(query: str, hint: Intent | None = None) -> Intent | None:
    """用 LLM 判定意图；失败时返回 None。"""
    hint_line = ""
    if hint:
        hint_line = (
            f"规则初判：{hint}（{INTENT_LABEL.get(hint, hint)}），仅供参考。"
            "以系统提示中的规程边界和判定顺序为准。\n"
        )
    try:
        result = await _chat().with_structured_output(IntentResult).ainvoke(
            [
                ("system", INTENT_PROMPT),
                ("human", f"{hint_line}用户问题：{query}"),
            ]
        )
        if isinstance(result, dict):
            result = IntentResult.model_validate(result)
        if not isinstance(result, IntentResult):
            trace("intent", intent="none")
            return None
        trace("intent", intent=result.intent, reason=result.reason, hint=hint or "")
        return result.intent
    except Exception as exc:
        trace("intent.error", error=type(exc).__name__)
        return None


async def rewrite_query(query: str, intent: Intent) -> str | None:
    """将问题改写为检索查询；失败时返回 None。"""
    try:
        result = await _chat().with_structured_output(RewriteResult).ainvoke(
            [
                ("system", _REWRITE_INSTRUCTION),
                ("human", f"意图：{intent}\n问题：{query}"),
            ]
        )
        if isinstance(result, RewriteResult):
            text = result.query.strip()
        elif isinstance(result, dict):
            text = RewriteResult.model_validate(result).query.strip()
        else:
            return None
        trace("rewrite", query=text or "")
        return text or None
    except Exception as exc:
        trace("rewrite.error", error=type(exc).__name__)
        return None
