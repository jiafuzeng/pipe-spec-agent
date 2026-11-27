"""Comparison, plan, and explanation answers grounded only in retrieved quotes."""

from __future__ import annotations

import re

METHODS = (
    ("CCTV", ("CCTV", "电视检测", "闭路电视")),
    ("QV", ("QV", "潜望镜")),
    ("声纳", ("声纳",)),
    ("人员进入", ("人员进入", "人工下井", "进入管内")),
    ("潜水", ("潜水",)),
)

_CALCULATION = re.compile(
    r"修复指数|养护指数|(?<![A-Za-z0-9_])(?:RI|MI)(?![A-Za-z0-9_])|缺陷分值|画.*曲线",
    re.I,
)
_DIAMETER = r"(?:DN\s*|管径(?:为|约)?\s*(?=\d+(?:\.\d+)?\s*(?:mm|毫米)))(\d+(?:\.\d+)?)"
_WATER = r"(?:水位|充满度)(?:约为|约|为)?\s*(?:管径的)?\s*(\d+(?:\.\d+)?)\s*[%％]"
_CONDITIONS = (
    (
        "积泥厚度是否埋没探头",
        r"(?:积泥|淤泥)?(?:已经|尚未|已|未|没有|不会|未能|未曾|可能)?(?:埋没|淹没|覆盖)探头",
    ),
    ("流速", r"流速(?:约为|约|为)?\s*\d+(?:\.\d+)?\s*(?:m/s|米/秒|米每秒)"),
    (
        "管段长度",
        r"(?:管段长度|管长)(?:约为|约|为)?\s*\d+(?:\.\d+)?\s*(?:km|mm|m|千米|公里|米)",
    ),
    ("有无竣工资料", r"(?:没有|缺少|已有|有|无)竣工资料|竣工资料(?:齐全|缺失)"),
)
_UNCERTAIN = re.compile(r"是否|有无|未知|不明|待测|待确认|不确定|可能|[?？]")


def classify_turn(query: str) -> str:
    if _CALCULATION.search(query):
        return "calculate"
    if "检测方案" in query or (
        "如何检测" in query and re.search(r"管径|水位|DN\s*\d", query, re.I)
    ):
        return "plan"
    if re.search(r"比较|对比|差异|区别", query) and (
        _requested(query) or re.search(r"检测方式|检测方法", query)
    ):
        return "compare"
    if "检查井" in query and re.search(r"先后|之前|之后|顺序", query):
        return "explain"
    if re.search(r"为何|为什么|能否单独", query) and re.search(r"声纳|检查井", query):
        return "explain"
    return "qa"


def _usable(evidence) -> list[dict]:
    return [item for item in evidence if item.get("clause_no") and item.get("quote")]


def _requested(query: str):
    found = []
    for name, aliases in METHODS:
        if _mentions(query, aliases):
            found.append((name, aliases))
    return found


def _mentions(text: str, aliases) -> bool:
    return any(alias.casefold() in text.casefold() for alias in aliases)


def answer_evidence(intent: str, query: str, evidence) -> list[dict]:
    rows = _usable(evidence)
    if intent == "compare":
        methods = _requested(query) or METHODS
        return [
            row
            for row in rows
            if any(_mentions(row["quote"], aliases) for _, aliases in methods)
        ]
    return rows


def render_compare(query: str, evidence, table: bool = False) -> str | None:
    evidence = answer_evidence("compare", query, evidence)
    if not evidence:
        return None
    requested = _requested(query)
    if not requested:
        requested = [
            item
            for item in METHODS
            if any(_mentions(row["quote"], item[1]) for row in evidence)
        ]
    sections = []
    conditions = []
    for name, aliases in requested:
        hits = [row for row in evidence if _mentions(row["quote"], aliases)]
        body = "\n".join(f"〔{item['clause_no']}〕{item['quote']}" for item in hits)
        sections.append(f"### {name}\n" + (body or "未检索到直接写明该方法的条款。"))
        for item in hits:
            for sentence in _sentences(item["quote"]):
                if _requested(sentence) == [(name, aliases)] and re.search(
                    r"适用|宜|不得|应|不小于|不大于|可用于", sentence
                ):
                    conditions.append(
                        f"{name} 须核对〔{item['clause_no']}〕「{sentence}」。"
                    )
                    break
            else:
                continue
            break
    conclusion = " ".join(conditions) or "本轮条款未明确给出所比较方法的选择条件。"
    ending = "选择结论：" + conclusion + " 仅凭本轮信息无法确定现场应选哪一种方法。"
    if table:
        lines = ["| 方法 | 条款 |", "| --- | --- |"]
        for name, aliases in requested:
            hits = [row for row in evidence if _mentions(row["quote"], aliases)]
            cell = "<br>".join(
                f"〔{item['clause_no']}〕{item['quote']}" for item in hits
            ) or "未检索到直接写明该方法的条款。"
            lines.append(f"| {name} | {cell} |")
        lines.append("")
        lines.append(ending)
        return "\n".join(lines)
    sections.append(ending)
    return "\n\n".join(sections)


def _known(query: str) -> list[str]:
    found = []
    diameter = re.search(_DIAMETER, query, re.I)
    if diameter:
        found.append(f"管径 DN{diameter.group(1)}")
    level = re.search(_WATER, query)
    if level:
        found.append(f"管内水位约 {level.group(1)}%")
    cover = re.search(r"埋深约?\s*(\d+(?:\.\d+)?)\s*m", query, re.I)
    if cover:
        found.append(f"埋深约 {cover.group(1)} m")
    if "污水" in query:
        found.append("污水管")
    if "雨水" in query:
        found.append("雨水管")
    for road in ("次干道", "主干道", "支管"):
        if road in query:
            found.append(road)
    if "不具备停水" in query or "不能停水" in query:
        found.append("现场不能停水降水")
    sediment = re.search(r"无积泥|没有积泥|积泥较厚|有积泥", query)
    if sediment:
        found.append(sediment[0])
    return found


def _number(query: str, pattern: str):
    match = re.search(pattern, query, re.I)
    return float(match.group(1)) if match else None


def _sentences(quote: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。；;\n]", quote) if part.strip()]


def _violations(query: str, evidence) -> list[str]:
    water = _number(query, _WATER)
    diameter = _number(query, _DIAMETER)
    rows = []
    for item in evidence:
        clause_methods = _requested(item["quote"])
        for sentence in _sentences(item["quote"]):
            methods = _requested(sentence)
            if len(methods) > 1:
                continue  # A shared sentence cannot safely attribute the limit.
            if not methods and len(clause_methods) == 1:
                methods = clause_methods
            method = methods[0][0] if methods else "该条款所述方法"
            limit = re.search(
                r"(?:水位|充满度)(?:应|均)?(?:不得|不宜|不应|不)(?:大于|超过)"
                r"\s*(?:(?:管径|管道直径)的?)?\s*(\d+(?:\.\d+)?)\s*(?:[%％]|/\s*(\d+))",
                sentence,
            )
            minimum = re.search(
                r"管径(?:应|宜)?(?:不小于|不得小于|不应小于|不宜小于)\s*(\d+)\s*(?:mm|毫米)",
                sentence,
                re.I,
            )
            facts = []
            if water is not None and limit:
                upper = float(limit[1])
                if limit[2]:
                    upper = (
                        upper * 100 / int(limit[2]) if int(limit[2]) else float("inf")
                    )
                if water > upper:
                    facts.append(f"管内水位约 {water:g}%")
            if diameter is not None and minimum and diameter < int(minimum[1]):
                facts.append(f"管径 DN{diameter:g}")
            if facts:
                rows.append(
                    f"〔{item['clause_no']}〕{'、'.join(facts)} 不满足「{sentence}」。因此不能采用{method}。"
                )
    return rows


def plan_conditions(query: str):
    known = _known(query)
    missing = []
    for pattern, label in ((_DIAMETER, "管径"), (_WATER, "水位")):
        if _number(query, pattern) is None:
            missing.append(label)
    phrases = re.split(r"[，,。；;\n]", query)
    for label, pattern in _CONDITIONS:
        for phrase in phrases:
            match = re.search(pattern, phrase, re.I)
            if match and not _UNCERTAIN.search(phrase):
                known.append(match[0])
                break
        else:
            missing.append(label)
    return known, missing


def render_plan(query: str, evidence) -> str | None:
    evidence = _usable(evidence)
    if not evidence:
        return None
    known, missing = plan_conditions(query)
    violations = _violations(query, evidence)
    lines = ["已知条件："]
    lines.extend(f"- {item}" for item in known)
    if not known:
        lines.append("- 用户原文未给出可核对的管径或水位")
    lines.append("")
    lines.append("缺失且会改变方法适用或安全结论的条件：")
    lines.extend(f"- {item}" for item in missing)
    if not missing:
        lines.append("- 无")
    lines.append("")
    lines.append("已给条件与条款对照：")
    if violations:
        lines.extend(f"- {item}" for item in violations)
    else:
        lines.append("- 本轮原文中的界限与已给条件没有冲突，或原文未写出可解析的界限。")
    lines.append("")
    lines.append("检索到的条款：")
    lines.extend(f"- 〔{item['clause_no']}〕{item['quote']}" for item in evidence)
    lines.append("")
    if missing:
        lines.append(
            "请补充上述缺失项。确认前不给出最终检测方法推荐。"
            "已引用条款中的「不得 / 应 / 不宜」仍然有效。"
        )
    else:
        lines.append(
            "关键条件已在原文中出现。安排只采用上面没有冲突的条款，不把未引用的方法写成推荐。"
        )
    return "\n".join(lines)


def render_explain(query: str, evidence) -> str | None:
    evidence = _usable(evidence)
    if not evidence:
        return None
    lines = []
    asks_why = re.search(r"为何|为什么|能否单独", query) is not None
    asks_order = re.search(r"之前|之后|先后", query) is not None
    for item in evidence:
        quote = item["quote"]
        lines.append(f"〔{item['clause_no']}〕{quote}")
        if (
            asks_why
            and "声纳" in quote
            and re.fullmatch(
                r"(?:[\d.]+\s+)?声纳检测(?:结果)?(?:不能|不得)单独作为结构性缺陷的判定依据[。.]?",
                quote.strip(),
            )
        ):
            lines.append("声纳不能单独作为结构性缺陷的判定依据。此处不补充规程外理由。")
        if asks_order and re.search(
            r"检查井检测(?:应|宜)?(?:安排)?在管道检测之前", quote
        ):
            lines.append(f"检查顺序见〔{item['clause_no']}〕原文。")
    return "\n".join(lines)
