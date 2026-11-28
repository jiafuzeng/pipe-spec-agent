"""LLM 意图识别与检索问题改写。"""

from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from app import settings

# 全局意图（规则初判 + LLM 共用）
# qa        普通规程问答 → ReAct 检索
# compare   检测方法对比 → ReAct，证据按方法名过滤
# explain   原理/顺序解释 → ReAct
# plan      检测方案规划 → ReAct
# chitchat  寒暄/身份询问 → 直答，不检索
Intent = Literal["qa", "compare", "explain", "plan", "chitchat"]

_INTENT_INSTRUCTION = """你是排水管道规程助手的意图分类器。只输出一个意图标签。

可选意图：
<ul>
<li><b>qa</b>：条款查阅、适用条件、一般规程问答</li>
<li><b>compare</b>：两种及以上检测方法的对比、差异、适用边界</li>
<li><b>explain</b>：原理、先后顺序、因果（如检查井与声纳为何如此安排）</li>
<li><b>plan</b>：按管径/水位等条件给出检测方案或「如何检测」规划</li>
<li><b>chitchat</b>：寒暄、打招呼、问助手身份/能力，与规程无关</li>
</ul>

规则：与规程相关但无法明确归入 compare/explain/plan 时选 qa；仅寒暄或身份类选 chitchat。"""

_REWRITE_INSTRUCTION = """你是排水管道规程（CJJ 181—2012）检索查询改写器。
根据用户问题与意图，改写成适合条款检索的简洁中文查询。

要求：
<ul>
<li>保留检测方法、管径、水位、条款主题等关键实体</li>
<li>去掉寒暄、口语赘词与无关背景</li>
<li>compare：突出需对比的检测方法与差异点</li>
<li>explain：突出原理、顺序或因果对象</li>
<li>plan：突出场景条件与检测方案诉求</li>
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
            return result.intent
        if isinstance(result, dict):
            return IntentResult.model_validate(result).intent
        return None
    except Exception:
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
        return text or None
    except Exception:
        return None
