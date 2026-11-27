"""聊天模型入口与结构化 LLM 调用。"""

import json
from typing import Literal, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from app.settings import chat

# 全局意图（规则初判 + LLM 共用）
# qa        普通规程问答 → ReAct 检索
# compare   检测方法对比 → ReAct，证据按方法名过滤
# explain   原理/顺序解释 → ReAct
# plan      检测方案规划 → ReAct
# chitchat  寒暄/身份询问 → 直答，不检索
Intent = Literal["qa", "compare", "explain", "plan", "chitchat"]

T = TypeVar("T", bound=BaseModel)


class IntentResult(BaseModel):
    """LLM 意图判定输出。"""

    intent: Intent


def chat_model() -> ChatOpenAI:
    """统一构造 OpenAI 兼容聊天模型（读 app.settings.chat）。"""
    cfg = chat()
    return ChatOpenAI(
        model=cfg.model,
        api_key=SecretStr(cfg.api_key),
        base_url=cfg.base_url,
        temperature=0,
        timeout=cfg.timeout,
    )


async def structured(model: type[T], instruction: str, inputs: object) -> T | None:
    """按 Pydantic 模型拉结构化结果；未就绪或失败时返回 None。"""
    if not chat().ready:
        return None
    try:
        llm = chat_model().with_structured_output(model)
        result = await llm.ainvoke(
            [
                ("system", instruction),
                ("human", json.dumps(inputs, ensure_ascii=False)),
            ]
        )
        if isinstance(result, model):
            return result
        if isinstance(result, dict):
            return model.model_validate(result)
        return None
    except Exception:
        return None
