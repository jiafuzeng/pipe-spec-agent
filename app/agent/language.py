"""LLM 意图识别与检索问题改写。"""

from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from app import settings
from log import chat_callbacks, trace

# 全局意图（规则初判 + LLM 共用）
# retrieve  基础条文与概念检索 → ReAct
# compare   检测方法与方案对比 → ReAct
# compute   计算推理、智能问数与可视化 → ReAct
# chitchat  闲聊 → 直答，不检索
Intent = Literal["retrieve", "compare", "compute", "chitchat"]

_INTENT_INSTRUCTION = """你是排水管道规程助手的意图分类器。只输出一个意图标签。

可选意图：
<ul>
<li><b>retrieve</b>：基础条文与概念检索。查条款、定义、适用条件、原理、程序、单种方法怎么用。</li>
<li><b>compare</b>：检测方法与方案对比。两种及以上方法/方案的差异、适用边界、如何取舍。</li>
<li><b>compute</b>：计算推理、智能问数与可视化。指数/评分计算、按数据作答、要图表或统计。</li>
<li><b>chitchat</b>：闲聊。寒暄、打招呼、问助手身份/能力，与规程无关。</li>
</ul>

规则：与规程相关但不是对比也不是计算/问数/可视化时选 retrieve；仅寒暄或身份类选 chitchat。"""

_REWRITE_INSTRUCTION = """你是排水管道规程（CJJ 181—2012）检索查询改写器。
根据用户问题与意图，改写成适合条款检索的简洁中文查询。

要求：
<ul>
<li>保留检测方法、管径、水位、条款主题、计算对象等关键实体</li>
<li>去掉寒暄、口语赘词与无关背景</li>
<li>retrieve：突出要查的条文主题或概念</li>
<li>compare：突出需对比的检测方法或方案与差异点</li>
<li>compute：突出计算对象、指标或要统计/可视化的量</li>
<li>只输出一条检索查询，不要解释</li>
</ul>"""


class IntentResult(BaseModel):
    """LLM 意图判定输出。"""

    intent: Intent


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


async def recognize_intent(query: str) -> Intent | None:
    """用 LLM 判定意图；失败时返回 None。"""
    try:
        result = await _chat().with_structured_output(IntentResult).ainvoke(
            [
                ("system", _INTENT_INSTRUCTION),
                ("human", query),
            ]
        )
        if isinstance(result, IntentResult):
            intent = result.intent
        elif isinstance(result, dict):
            intent = IntentResult.model_validate(result).intent
        else:
            intent = None
        trace("intent", intent=intent or "none")
        return intent
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
