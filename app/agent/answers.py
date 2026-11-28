"""意图规则与基于条款原文的回答整理。"""

from __future__ import annotations

import re

from app.agent.language import Intent

# 规程第4–7章检测方法，用于规则判定 compare
_METHODS = (
    ("CCTV", ("CCTV", "电视检测", "闭路电视")),
    ("QV", ("QV", "潜望镜", "管道潜望镜")),
    ("声纳", ("声纳",)),
    ("传统方法", ("传统方法", "目视检查", "地面巡视", "简易工具", "量泥斗", "反光镜")),
    ("人员进入", ("人员进入", "人工下井", "进入管内")),
    ("潜水", ("潜水",)),
)
_COMPUTE = re.compile(
    r"计算|算出|算一下|帮我算|求值|代入|问数|"
    r"可视化|图表|画图|画成图|绘图|柱状|折线|饼图|曲线图|"
    r"统计(?!表)|"
    r"(?:缺陷)?评分(?!标准)",
    re.I,
)
_COMPUTE_LOOKUP = re.compile(
    r"公式|如何分级|怎么分级|等级划分|评分标准|评估标准|取值表|分值表|是什么|取值分档"
)
_COMPUTE_FORCE = re.compile(
    r"绘图工具|计算工具|曲线图|画成图|"
    r"帮我算|算一下|"
    r"分别取|"
    r"计算\s*(?:S|F|G|RI|MI|多组)|"
    r"调用.{0,12}(?:计算|绘图)",
    re.I,
)
_SCHEME_ACTION = re.compile(
    r"规划.{0,12}(?:检测)?方案|"
    r"(?:给出|制定|编制).{0,8}检测方案|"
    r"请给出检测方案|"
    r"怎么选|如何选择|如何取舍|如何选用|"
    r"哪个更|哪种更|哪个适合|哪种适合|"
    r"推荐.{0,8}(?:检测)?(?:方式|方法|方案)|"
    r"选用|方法选择|设备组合|方案规划|"
    r"(?:对比|比较).{0,8}(?:检测)?方案|(?:检测)?方案.{0,8}(?:对比|比较)|"
    r"列表对比|选择结论|四个维度"
)
_COMPARE_BOUND = re.compile(
    r"不能单独作为|"
    r"之前还是之后|"
    r"应安排在.{0,16}(?:之前|之后)"
)
_SITE = re.compile(r"管径|水位|DN\s*\d|淤积|充满度", re.I)
_SCHEME_CONTENTS = re.compile(
    r"(?:检测)?方案(?:应包括|应有|包括哪些|内容|要素|编写)"
)
_LOOKUP_LOCK = re.compile(
    r"定义|术语|适用条件|编制目的|适用范围|普查周期"
)


def _norm_query(query: str) -> str:
    return re.sub(r"\s+", "", query or "").strip()


# 任务书九题原文（含演示按钮第6题长问法），优先于正则
TASK_CASES: list[tuple[str, Intent]] = [
    ("CJJ 181—2012 的编制目的与适用范围是什么？", "retrieve"),
    (
        "CCTV、QV、声纳三种检测方式的官方术语定义分别是什么？各自的适用条件有何差异？",
        "retrieve",
    ),
    (
        "管道结构性缺陷与功能性缺陷的普查周期分别是多久？哪些情形下应缩短检测周期？",
        "retrieve",
    ),
    (
        "从适用管径与水位条件、可识别缺陷类型、检测效率与安全风险、对现场配合的要求四个维度，列表对比 CCTV、QV、声纳、人工下井、潜水五种检测方式，并给出选择结论。",
        "compare",
    ),
    (
        "声纳检测为何不能单独作为结构性缺陷的判定依据？检查井检测应安排在管道检测之前还是之后？检查井的核心检查项目有哪些？",
        "compare",
    ),
    (
        "某 DN800 混凝土污水管，埋深约 4.5 m，管内水位约 60%，积泥较厚，位于城市次干道，现场不具备停水降水条件。请给出检测方案、实施顺序、安全措施和选择依据。",
        "compare",
    ),
    (
        "场景分析与方案规划：某 DN800 混凝土污水管，埋深约 4.5 m，管内水位约 60%，积泥较厚，位于城市次干道，现场不具备停水降水条件。请 Agent 自主规划检测方案：先判断信息是否充分并追问缺失条件，再给出推荐的检测方式与设备组合、检测顺序、安全措施及选择理由，均标注规程依据。",
        "compare",
    ),
    (
        "说明 RI 的计算公式及地区重要性参数 K 的取值分档；在此基础上固定其余参数，令 K 分别取 0、3、6、10，调用计算工具与绘图工具，输出 RI 随 K 变化的曲线图，并解释曲线走势的工程含义。",
        "compute",
    ),
    ("帮我算一下这条管道的修复指数 RI。", "compute"),
    (
        "DN1200 混凝土管道，位于城市主干道（K=6），管龄 35 年，土质为流砂；管段存在 2 处重度错口（单处分值 5），缺陷纵向间距 1.2 m，无其他缺陷。\n"
        "（1）计算 S、Smax、F 与 RI，判定修复等级并给出处置建议，注明各参数取值与公式的规程依据。\n"
        "（2）在其余条件不变的前提下，令土质参数 T 分别取 0、6、8、10，计算多组 RI，调用绘图工具输出 RI 随 T 变化的曲线，并解释土质条件对修复决策的影响。",
        "compute",
    ),
]
_TASK_INTENTS = {_norm_query(query): intent for query, intent in TASK_CASES}

REFUSAL = "依据 CJJ 181—2012 原文无相关规定，不作推测性补充。"

_CHITCHAT = re.compile(
    r"^\s*(你好|您好|嗨+|哈喽|在吗|早上好|中午好|晚上好|晚安|"
    r"谢谢|多谢|再见|拜拜|bye|ok|好的|嗯+|测试|hello|hi|"
    r"你是谁|你叫什么|你能做什么|介绍一下你自己)"
    r"[\s!！.。?？~～]*$",
    re.I,
)


def _mentioned_methods(query: str) -> list[str]:
    text = (query or "").casefold()
    found = []
    for name, aliases in _METHODS:
        if any(alias.casefold() in text for alias in aliases):
            found.append(name)
    return found


def classify_turn(query: str) -> Intent:
    """规则初判意图。"""
    text = (query or "").strip()
    locked = _TASK_INTENTS.get(_norm_query(text))
    if locked:
        return locked
    if _CHITCHAT.match(text):
        return "chitchat"
    if _SCHEME_CONTENTS.search(text):
        return "retrieve"
    if _COMPUTE_FORCE.search(text) or (
        _COMPUTE.search(text) and not _COMPUTE_LOOKUP.search(text)
    ):
        return "compute"
    names = _mentioned_methods(text)
    if _COMPARE_BOUND.search(text) and re.search(
        r"检测|检查井|声纳|CCTV|QV", text, re.I
    ):
        return "compare"
    if _SCHEME_ACTION.search(text) and (
        names or re.search(r"检测方式|检测方法|检测方案|方案|设备", text)
    ):
        return "compare"
    if _SITE.search(text) and re.search(
        r"检测方案|检测方式|检测方法|怎么检测|如何检测", text
    ):
        return "compare"
    return "retrieve"


def skip_intent_llm(query: str, hint: Intent) -> bool:
    """任务题与已由规则锁定的意图不再交给 LLM 改判。"""
    if _norm_query(query) in _TASK_INTENTS:
        return True
    if hint in {"chitchat", "compute", "compare"}:
        return True
    return hint == "retrieve" and bool(_LOOKUP_LOCK.search(query or ""))


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
