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
_MAX_CLAUSES = 4


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
    return compress_items([item], query)


def compress_items(items: list, query: str = "") -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for item in items or []:
        eid = item.get("evidence_id") or ""
        for row in _expand(item):
            score = _score(query, row["clause_no"], row["quote"]) if query else 1
            scored.append((score, dict(row, evidence_id=eid)))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    packed: list[dict] = []
    seen: set[str] = set()
    for score, row in scored:
        clause = row["clause_no"]
        if clause in seen:
            continue
        if query and packed and score <= 0:
            continue
        seen.add(clause)
        packed.append(row)
        if len(packed) >= _MAX_CLAUSES:
            break
    return packed


def render_clauses(rows: list[dict]) -> str:
    """模型可见的紧凑条文，一行一条。"""
    if not rows:
        return "未命中相关条款原文。"
    return "\n".join(f"{row['clause_no']} {row['quote']}" for row in rows)
