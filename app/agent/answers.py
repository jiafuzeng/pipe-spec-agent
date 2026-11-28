"""意图规则与基于条款原文的回答整理。"""

from __future__ import annotations

import re

from app.agent.language import Intent

# 检测方法别名，用于规则判定 compare
_METHODS = (
    ("CCTV", ("CCTV", "电视检测", "闭路电视")),
    ("QV", ("QV", "潜望镜")),
    ("声纳", ("声纳",)),
    ("人员进入", ("人员进入", "人工下井", "进入管内")),
    ("潜水", ("潜水",)),
)

REFUSAL = "依据 CJJ 181—2012 原文无相关规定，不作推测性补充。"

_CHITCHAT = re.compile(
    r"^\s*(你好|您好|嗨+|哈喽|在吗|早上好|中午好|晚上好|晚安|"
    r"谢谢|多谢|再见|拜拜|bye|ok|好的|嗯+|测试|hello|hi|"
    r"你是谁|你叫什么|你能做什么|介绍一下你自己)"
    r"[\s!！.。?？~～]*$",
    re.I,
)


def _named_method(query: str) -> bool:
    text = (query or "").casefold()
    return any(
        alias.casefold() in text for _, aliases in _METHODS for alias in aliases
    )


def classify_turn(query: str) -> Intent:
    """规则初判意图。"""
    text = (query or "").strip()
    if _CHITCHAT.match(text):
        return "chitchat"
    if "检测方案" in text or (
        "如何检测" in text and re.search(r"管径|水位|DN\s*\d", text, re.I)
    ):
        return "plan"
    if re.search(r"比较|对比|差异|区别", text) and (
        _named_method(text) or re.search(r"检测方式|检测方法", text)
    ):
        return "compare"
    if "检查井" in text and re.search(r"先后|之前|之后|顺序", text):
        return "explain"
    if re.search(r"为何|为什么|能否单独", text) and re.search(r"声纳|检查井", text):
        return "explain"
    return "qa"


def normalize_citations(text: str) -> str:
    """将 [条款] / 【条款】 统一为 〔条款〕，再从正文去掉条款标记。"""
    if not text:
        return text
    text = re.sub(r"\[(\d+\.\d+(?:\.\d+)?)\]", r"〔\1〕", text)
    text = re.sub(r"【(\d+\.\d+(?:\.\d+)?)】", r"〔\1〕", text)
    # 正文不再展示条款号；引用走 evidence / citations
    text = re.sub(r"\s*〔[^〕]+〕", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def format_answer(intro: str, sections) -> str:
    """拼标准回答：开场 + ### 方面。"""
    parts = []
    lead = normalize_citations((intro or "").strip())
    if lead:
        parts.append(lead)
    for section in sections or []:
        if isinstance(section, dict):
            title = str(section.get("title") or "").strip()
            body = normalize_citations(str(section.get("body") or "").strip())
        else:
            title = str(getattr(section, "title", "") or "").strip()
            body = normalize_citations(str(getattr(section, "body", "") or "").strip())
        if not title or not body:
            continue
        parts.append(f"### {title}\n{body}")
    return "\n\n".join(parts)


def grounded_summary(evidence) -> str | None:
    """无模型草稿时，按条款拼成标准开场+分节。"""
    sections = []
    seen = set()
    for item in evidence or []:
        number = item.get("clause_no")
        quote = str(item.get("quote") or "").strip()
        if not number or not quote or number in seen:
            continue
        seen.add(number)
        body = re.sub(rf"^{re.escape(str(number))}\s*", "", quote).strip()
        sentence = re.split(r"(?<=[。；])", body, maxsplit=1)[0].strip().rstrip("。；")
        if sentence:
            sections.append({"title": str(number), "body": sentence + "。"})
    if not sections:
        return None
    return format_answer("结合已检索到的规程条款，可以这样理解：", sections)
