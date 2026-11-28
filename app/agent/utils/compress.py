"""把检索原文压成给模型看的条款短句：按查询挑 span，不按字数裁切。"""

from __future__ import annotations

import re

from app.knowledge.retrieval import clause_mentioned

_BLANK = re.compile(r"\s+")
_STOP = {
    "管道",
    "排水",
    "城镇",
    "检测",
    "评估",
    "应当",
    "可以",
    "进行",
    "采用",
    "根据",
    "以及",
    "或者",
    "规定",
    "基本",
}
_MAX_CLAUSES = 8


def compact(text: str) -> str:
    """合并空白并去掉标题标记，保留全部文字。"""
    return _BLANK.sub(" ", re.sub(r"^#+\s*", "", (text or "").strip()))


def _keys(text: str) -> set[str]:
    keys: set[str] = set()
    for phrase in re.findall(r"[\u3400-\u9fff]{2,}", text or ""):
        for i in range(len(phrase) - 1):
            bigram = phrase[i : i + 2]
            if bigram not in _STOP:
                keys.add(bigram)
    keys.update(re.findall(r"[a-z0-9]+", (text or "").lower()))
    return keys


def _heading(quote: str) -> bool:
    return (not re.search(r"[。；：:]", quote)) and len(quote) < 24


def _score(query: str, clause: str, quote: str) -> int:
    if clause and clause_mentioned(clause, query):
        return 1000
    return len(_keys(query) & _keys(f"{clause} {quote}"))


def _expand(item: dict) -> list[dict]:
    best: dict[str, str] = {}
    for span in item.get("citation_spans") or []:
        clause = str(span.get("clause") or item.get("clause_no") or "").strip()
        quote = compact(span.get("quote") or "")
        if not clause or not quote or _heading(quote):
            continue
        if clause not in best or len(quote) > len(best[clause]):
            best[clause] = quote
    if best:
        return [{"clause_no": clause, "quote": quote} for clause, quote in best.items()]
    quote = compact(item.get("quote") or "")
    if not quote:
        return []
    return [{"clause_no": item.get("clause_no") or "", "quote": quote}]


def compress_item(item: dict, query: str = "") -> list[dict]:
    """按 citation_spans 拆条款；有查询时只留对得上的，不裁切条文本身。"""
    rows = _expand(item)
    if not query or len(rows) <= 1:
        return rows
    scored = [(_score(query, row["clause_no"], row["quote"]), row) for row in rows]
    best = max(score for score, _ in scored)
    if best <= 0:
        target = str(item.get("clause_no") or "")
        for _, row in scored:
            if row["clause_no"] == target:
                return [row]
        return [scored[0][1]]
    return [
        row
        for score, row in scored
        if score == best or (score >= 2 and score * 2 >= best)
    ]


def compress_items(items: list, query: str = "") -> list[dict]:
    packed: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        for row in compress_item(item, query):
            clause = row["clause_no"]
            if clause in seen:
                continue
            seen.add(clause)
            packed.append(row)
            if len(packed) >= _MAX_CLAUSES:
                return packed
    return packed
