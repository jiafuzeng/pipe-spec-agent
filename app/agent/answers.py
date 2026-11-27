"""意图规则与基于条款原文的回答整理。"""

from __future__ import annotations

import re

from app.agent.language import Intent

# 检测方法标准名 → 口语/规程别名，用于对比类问题过滤证据
METHODS = (
    ("CCTV", ("CCTV", "电视检测", "闭路电视")),
    ("QV", ("QV", "潜望镜")),
    ("声纳", ("声纳",)),
    ("人员进入", ("人员进入", "人工下井", "进入管内")),
    ("潜水", ("潜水",)),
)

REFUSAL = "依据 CJJ 181—2012 原文无相关规定，不作推测性补充。"

# 整句寒暄/身份询问，命中则走闲聊直答
_CHITCHAT = re.compile(
    r"^\s*(你好|您好|嗨+|哈喽|在吗|早上好|中午好|晚上好|晚安|"
    r"谢谢|多谢|再见|拜拜|bye|ok|好的|嗯+|测试|hello|hi|"
    r"你是谁|你叫什么|你能做什么|介绍一下你自己)"
    r"[\s!！.。?？~～]*$",
    re.I,
)


def classify_turn(query: str) -> Intent:
    """规则初判意图，取值见 language.Intent。"""
    text = (query or "").strip()
    if _CHITCHAT.match(text):
        return "chitchat"
    if "检测方案" in text or (
        "如何检测" in text and re.search(r"管径|水位|DN\s*\d", text, re.I)
    ):
        return "plan"
    if re.search(r"比较|对比|差异|区别", text) and (
        _requested(text) or re.search(r"检测方式|检测方法", text)
    ):
        return "compare"
    if "检查井" in text and re.search(r"先后|之前|之后|顺序", text):
        return "explain"
    if re.search(r"为何|为什么|能否单独", text) and re.search(r"声纳|检查井", text):
        return "explain"
    return "qa"


def _usable(evidence) -> list[dict]:
    """保留同时有条款号与引文的证据。"""
    return [item for item in evidence if item.get("clause_no") and item.get("quote")]


def _requested(query: str):
    """问题里点名的检测方法列表。"""
    return [
        (name, aliases)
        for name, aliases in METHODS
        if any(alias.casefold() in (query or "").casefold() for alias in aliases)
    ]


def _mentions(text: str, aliases) -> bool:
    """文本是否命中任一检测方法别名。"""
    return any(alias.casefold() in text.casefold() for alias in aliases)


def answer_evidence(intent: str, query: str, evidence) -> list[dict]:
    """按意图整理证据；对比类只保留与点名方法相关的条款。"""
    rows = _usable(evidence)
    if intent != "compare":
        return rows
    methods = _requested(query) or METHODS
    return [
        row
        for row in rows
        if any(_mentions(row["quote"], aliases) for _, aliases in methods)
    ]


def normalize_citations(text: str) -> str:
    """将 [条款] / 【条款】 统一为 〔条款〕。"""
    if not text:
        return text
    text = re.sub(r"\[(\d+\.\d+(?:\.\d+)?)\]", r"〔\1〕", text)
    text = re.sub(r"【(\d+\.\d+(?:\.\d+)?)】", r"〔\1〕", text)
    return text


def _clause_sentence(item: dict) -> str:
    """从引文中取首句，并去掉开头重复的条款号。"""
    number = str(item.get("clause_no") or "")
    body = str(item.get("quote") or "").strip()
    body = re.sub(rf"^{re.escape(number)}\s*", "", body).strip()
    sentence = re.split(r"(?<=[。；])", body, maxsplit=1)[0].strip()
    return sentence or body


def grounded_summary(evidence) -> str | None:
    """按条款去重后拼「原文句〔条款号〕」，无可用证据则返回 None。"""
    lines = []
    seen = set()
    for item in _usable(evidence):
        if item["clause_no"] in seen:
            continue
        seen.add(item["clause_no"])
        sentence = _clause_sentence(item).rstrip("。；")
        if sentence:
            lines.append(f"{sentence}〔{item['clause_no']}〕。")
    if not lines:
        return None
    return "\n".join(lines)
