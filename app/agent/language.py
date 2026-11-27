"""Model suggestions are limited to intent labels, retrieval questions and quoted slots."""

import json
import os
import re

import httpx
from pydantic import BaseModel, Field
from typing import Literal


class Plan(BaseModel):
    intent: Literal["qa", "compare", "explain", "plan", "calculate"]
    questions: list[str] = Field(default_factory=list, max_length=4)


class Slot(BaseModel):
    name: str
    value: str
    quote: str = Field(min_length=1)


class Extraction(BaseModel):
    slots: list[Slot] = Field(default_factory=list, max_length=30)


async def structured(model, instruction, inputs):
    if os.getenv("AGENT_MODEL_ENABLED", "1") == "0" or not all(
        os.getenv(key) for key in ("CHAT_MODEL", "CHAT_BASE_URL")
    ):
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                os.environ["CHAT_BASE_URL"].rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + os.getenv("CHAT_API_KEY", "")},
                json={
                    "model": os.environ["CHAT_MODEL"],
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "system",
                            "content": instruction
                            + " 仅返回 JSON，格式："
                            + json.dumps(model.model_json_schema(), ensure_ascii=False),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(inputs, ensure_ascii=False),
                        },
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            return model.model_validate_json(
                re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
            )
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


async def extract_slots(query, fields):
    result = await structured(
        Extraction,
        "只抽取用户明确提供且属于字段的值。逐项逐字引用含字段和值的原句。"
        "不推导系数，不映射管径、道路或土质，不提取假设、未知或曲线扫描值。",
        {"消息": query, "可用字段": fields},
    )
    facts = {}
    for item in result.slots if result else []:
        field = next((f for f in fields if f["name"] == item.name), None)
        if not field or item.quote not in query or item.value not in item.quote:
            continue
        if not any(
            label in item.quote
            for label in (item.name, field.get("label_zh") or item.name)
        ):
            continue
        if re.search("假设|如果|未知|不确定|还是|或者", item.quote):
            continue
        facts[item.name] = item.value
    return facts
