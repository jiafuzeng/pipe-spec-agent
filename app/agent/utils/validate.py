"""回答相关性校验，并按标准结构重写。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.answers import REFUSAL, format_answer, normalize_citations
from app.agent.language import _chat
from app.agent.prompts import ANSWER_FORMAT
from app.agent.utils.compress import compress_item


_VALIDATE_INSTRUCTION = f"""你是排水管道规程回答的定稿编辑。
对照「用户问题」改写「草稿」，只保留用户真正关心的内容，并筛证据。

{ANSWER_FORMAT}

另外：
- intro：一两句口语，直接回答问题。
- sections：每个元素对应问题里的一个方面（title 用用户能听懂的叫法，body 用完整句子）。
- 删掉草稿里跑题、附带、扩展的条目。
- keep_evidence_ids 只留支撑这些问题的 evidence_id。
- 草稿完全跑题且证据无用时，intro 写拒答短句，sections 为空。
"""


class AnswerSection(BaseModel):
    """一个用户关心的方面。"""

    title: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=1, max_length=400)


class ValidateResult(BaseModel):
    """校验后的结构化回答。"""

    intro: str = Field(min_length=1, description="口语开场，直接回答问题")
    sections: list[AnswerSection] = Field(default_factory=list)
    keep_evidence_ids: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)


def _pack_evidence(evidence: list, query: str = "") -> str:
    lines = []
    for item in evidence or []:
        eid = item.get("evidence_id") or ""
        for row in compress_item(item, query):
            lines.append(
                f"- id={eid} clause={row['clause_no']} quote={row['quote']}"
            )
    return "\n".join(lines) or "（无证据）"


def _keep_evidence(evidence: list, wanted: set[str]) -> list:
    if not wanted:
        return evidence
    kept = [
        item
        for item in evidence
        if item.get("evidence_id") in wanted or item.get("clause_no") in wanted
    ]
    return kept or evidence


async def validate_answer(
    query: str, draft: str, evidence: list
) -> tuple[str, list, list[str]]:
    """返回 (markdown, kept_evidence, dropped_notes)。失败时按草稿回退。"""
    draft = normalize_citations(draft or "") or REFUSAL
    if not evidence:
        return draft, [], []
    try:
        result = await _chat().with_structured_output(ValidateResult).ainvoke(
            [
                ("system", _VALIDATE_INSTRUCTION),
                (
                    "human",
                    f"用户问题：{query}\n\n草稿回答：\n{draft}\n\n证据列表：\n"
                    f"{_pack_evidence(evidence, query)}",
                ),
            ]
        )
        if isinstance(result, dict):
            result = ValidateResult.model_validate(result)
        if not isinstance(result, ValidateResult):
            return draft, evidence, []
        text = format_answer(result.intro, result.sections) or draft
        kept = _keep_evidence(evidence, set(result.keep_evidence_ids or []))
        return text, kept, list(result.dropped or [])
    except Exception:
        return draft, evidence, []
