"""One bounded LangGraph for HTTP turns and the evaluation runner."""

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.agent.answers import (
    answer_evidence,
    classify_turn,
    render_compare,
    render_explain,
    render_plan,
    plan_conditions,
)
from app.agent.store import Store, now
from app.agent.defect_inputs import observations
from app.agent.language import Plan, extract_slots, structured
from app.integrations.mcp_client import call_tool
from app.rag.evidence import search_clauses, select_evidence

REFUSAL = "依据 CJJ 181—2012 原文无相关规定，不作推测性补充。"
WORKSTATION_ID = "workbench"
MEMORY_NAMESPACE = (WORKSTATION_ID, "memories")
MEMORY_LIMIT = 3


class State(TypedDict, total=False):
    query: str
    intent: str
    questions: list[str]
    candidates: list
    evidence: list
    missing_topics: list
    kind: str
    schema: dict
    values: dict
    route: str
    ids: list
    resume_at: str
    active_subject_id: str
    confirmed: list
    pending: list
    recent_values: list
    reused: dict
    reused_note: str


@dataclass
class Turn:
    store: Store
    run: str
    turn: str
    subject: dict
    version: int
    queue: asyncio.Queue
    tool_client: object = None
    session_id: str = ""

    def emit(self, kind, data, status="running"):
        event = self.store.event(
            self.run, self.turn, kind, data, status, self.subject, self.version
        )
        self.version += 1
        self.queue.put_nowait(event)

    async def tool(self, name, args):
        step = uuid.uuid5(
            uuid.NAMESPACE_URL, json.dumps([self.turn, name, args], sort_keys=True)
        ).hex
        cached = self.store.completed_tool(step)
        if cached is not None:
            return cached
        self.store.record_step(step, self.run, name, args)
        start = time.monotonic()
        for attempt in range(2):
            try:
                output = await (self.tool_client or call_tool)(name, args)
                break
            except TimeoutError:
                output = {"error": "TOOL_TIMEOUT"}
                if name != "calculate_index":
                    break
            except Exception:
                output = {"error": "TOOL_UNAVAILABLE"}
                break
        self.emit(
            "tool_call",
            dict(
                tool=name,
                inputs=args,
                output=output,
                call_id=step,
                step_id=step,
                elapsed_ms=round(1000 * (time.monotonic() - start)),
                attempts=attempt + 1,
                status="failed" if "error" in output else "succeeded",
            ),
        )
        self.store.record_step(step, self.run, name, args, output)
        if "error" in output:
            self.emit(
                "error",
                dict(
                    code=output["error"],
                    text=output.get("message", output["error"]),
                    retryable=output["error"] in {"TOOL_TIMEOUT", "TOOL_UNAVAILABLE"},
                ),
                "failed",
            )
        return output


def _confirmed_rows(slots, subject_id, kind, turn_id):
    rows = []
    for name, slot in slots.items():
        if not slot.get("confirmed"):
            continue
        rows.append(
            {
                "name": name,
                "value": slot.get("value"),
                "unit": slot.get("unit"),
                "subject_id": subject_id,
                "source_turn_id": slot.get("source_turn_id") or turn_id,
                "confirmed": True,
                "kind": kind,
            }
        )
    return rows


def uuid7():
    unix_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    return uuid.UUID(int=(unix_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b)


def _stamp(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def memory_view(item):
    return {
        "namespace": list(item.namespace),
        "key": item.key,
        "value": dict(item.value or {}),
        "created_at": _stamp(item.created_at),
        "updated_at": _stamp(item.updated_at),
    }


def _memory_action(query):
    if "忘记" in query:
        return "forget"
    if re.search(r"还记得什么|记得什么|查看记忆", query):
        return "list"
    if "记住" in query:
        return "remember"
    return None


def _memory_line(item):
    data = (item.value or {}).get("data", "")
    return f"{data}（{_stamp(item.updated_at)}，不是规程依据）"


async def _search_memories(store, query, limit=MEMORY_LIMIT):
    return await store.asearch(MEMORY_NAMESPACE, query=query, limit=limit)


def _active_subject(state, ctx):
    return state.get("active_subject_id") or ctx.subject.get("subject_id") or "default"


async def _memory_turn(state: State, runtime: Runtime[Turn], action: str):
    ctx = runtime.context
    store = runtime.store
    query = state["query"]
    active = _active_subject(state, ctx)
    if action == "list":
        found = await _search_memories(store, query)
        short_term = [
            item
            for item in (state.get("confirmed") or [])
            if item.get("subject_id") == active
        ]
        lines = ["当前对话正在用的："]
        lines.extend(
            [f"- {item['name']}={item['value']}" for item in short_term] or ["- 无"]
        )
        lines.append("以后还会记得的：")
        lines.extend(
            [f"- {_memory_line(item)}" for item in found]
            or ["- 没有可召回的长期记忆"]
        )
        ctx.emit(
            "answer",
            dict(
                text="\n".join(lines),
                short_term=short_term,
                long_term=[memory_view(item) for item in found],
            ),
            "completed",
        )
        return {"route": "end"}
    if action == "forget":
        found = await store.asearch(MEMORY_NAMESPACE, limit=100)
        named = next((item for item in found if item.key and item.key in query), None)
        if named is None:
            hint = re.sub(r"^.*忘记", "", query).strip(" ：:，,。")
            matches = [
                item
                for item in found
                if hint and hint in str((item.value or {}).get("data", ""))
            ]
            named = matches[0] if len(matches) == 1 else None
        confirmed = list(state.get("confirmed") or [])
        if named is None:
            text = "没有这一条"
        else:
            await store.adelete(MEMORY_NAMESPACE, named.key)
            data = str((named.value or {}).get("data", ""))
            confirmed = [
                item
                for item in confirmed
                if f"{item.get('name')}={item.get('value')}" not in data
            ]
            text = "已忘记。当前对话也不再沿用。"
        left = await _search_memories(store, query)
        ctx.emit(
            "answer",
            dict(text=text, long_term=[memory_view(item) for item in left]),
            "completed",
        )
        return {"route": "end", "confirmed": confirmed}
    pieces = [query.strip()]
    confirmed = [
        item
        for item in (state.get("confirmed") or [])
        if item.get("confirmed") and item.get("subject_id") in (None, active)
    ]
    if confirmed:
        pieces.append(
            "管段 "
            + active
            + " "
            + " ".join(
                f"{item['name']}={item['value']}{item.get('unit') or ''}"
                for item in confirmed
            )
        )
    data = " ".join(pieces)
    await store.aput(MEMORY_NAMESPACE, str(uuid7()), {"data": data})
    ctx.emit("answer", dict(text=f"已记住，不是规程依据：{data}"), "completed")
    return {"route": "end"}


async def plan(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context
    q = state["query"]
    action = _memory_action(q)
    if action and runtime.store is not None:
        return await _memory_turn(state, runtime, action)
    intent = classify_turn(q)
    if ctx.subject.get("continuing"):
        if ctx.subject.get("pending") == "plan":
            intent = "plan"
            q = q + "。" + ctx.subject.get("plan_query", "")
        else:
            intent = "calculate"
    kind = ctx.subject.get("pending") if ctx.subject.get("continuing") else None
    kind = kind or (
        "MI"
        if re.search("养护|MI", q, re.I)
        else "defect_score"
        if "缺陷分值" in q
        else "RI"
    )
    questions = []
    if intent != "calculate":
        questions = [q]
        if "声纳" in q and "检查井" in q:
            questions = [
                "声纳检测对结构性缺陷的判定依据",
                "检查井检查与管道检测的先后顺序",
            ]
            if re.search("项目|内容|哪些", q):
                questions.append("检查井检查项目与内容")
    elif re.search("说明|解释|分档|公式", q):
        questions = [f"{kind} 计算公式及参数取值分档"]
    if intent == "qa" and not re.search(r"第?\d+\.\d+\.\d+|补贴|收费", q):
        proposal = await structured(
            Plan,
            "分类规程问答意图，条文复合问题可拆成至多四个检索子问。"
            "不生成计算数据或工具调用。",
            {"问题": q},
        )
        if proposal:
            intent = proposal.intent
            questions = [
                v.strip() for v in proposal.questions if 0 < len(v.strip()) <= 300
            ]
            if not questions and intent != "calculate":
                questions = [q]
    ctx.emit(
        "plan_step",
        dict(
            text="检索已审核规程条款" if questions else "检查已发布计算规则",
            questions=questions,
            status="running",
        ),
    )
    return dict(
        intent=intent,
        query=q,
        kind=kind,
        questions=questions,
        route="retrieve" if questions else "schema",
    )


async def retrieve(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context

    async def search(q):
        start = time.monotonic()
        try:
            hits = (await asyncio.to_thread(search_clauses, q))["evidence"]
            status = "succeeded"
        except Exception:
            hits, status = [], "failed"
        ctx.emit(
            "tool_call",
            dict(
                tool="search_clauses",
                inputs={"query": q},
                status=status,
                call_id=uuid.uuid4().hex,
                elapsed_ms=round(1000 * (time.monotonic() - start)),
                via="in_process",
                summary=f"{len(hits)} 条候选",
            ),
        )
        return q, hits, status

    return {
        "candidates": await asyncio.gather(*(search(q) for q in state["questions"]))
    }


async def verify(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context
    evidence, missing = {}, []
    failures = 0
    for q, hits, status in state["candidates"]:
        try:
            if status == "failed":
                raise RuntimeError
            items = await select_evidence(q, hits)
        except Exception:
            failures += 1
            items = []
        if state["intent"] in {"compare", "plan", "explain"}:
            items = answer_evidence(state["intent"], state["query"], items)
        if not items:
            missing.append(q)
        for item in items:
            evidence[item["evidence_id"]] = item
    if failures:
        terminal = (
            failures == len(state["questions"]) and state["intent"] != "calculate"
        )
        ctx.emit(
            "error",
            dict(
                code="TOOL_UNAVAILABLE",
                text="部分条款检索或核对失败，可重试。",
                retryable=True,
            ),
            "failed" if terminal else "running",
        )
        if terminal:
            return {"route": "end"}
    for item in evidence.values():
        ctx.emit("evidence", item)
    return dict(
        evidence=list(evidence.values()), missing_topics=missing, route="answer"
    )


async def answer(state: State, runtime: Runtime[Turn]):
    q, intent, items = state["query"], state["intent"], state["evidence"]
    table = False
    if runtime.store is not None and intent == "compare":
        remembered = await _search_memories(runtime.store, q)
        table = any("表格" in str((item.value or {}).get("data", "")) for item in remembered)
    render = {
        "compare": lambda query, evidence: render_compare(query, evidence, table=table),
        "plan": render_plan,
        "explain": render_explain,
    }.get(intent)
    text = (
        render(q, items)
        if render
        else "\n".join(f"〔{i['clause_no']}〕{i['quote']}" for i in items)
    )
    if items and (re.search("补贴|收费", q) or state["missing_topics"]):
        text += "\n" + "、".join(state["missing_topics"]) + " " + REFUSAL
    status = "running" if intent == "calculate" else "completed"
    if intent == "plan" and items:
        _, missing = plan_conditions(q)
        runtime.context.subject.update(
            plan_query=q, missing=missing, pending="plan" if missing else None
        )
        if missing:
            status = "waiting_clarification"
    runtime.context.emit(
        "answer",
        dict(text=text or REFUSAL, citations=[i["evidence_id"] for i in items]),
        status,
    )
    return {"route": "schema" if intent == "calculate" else "end"}


async def schema(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context
    args = {"calculation_type": state["kind"]}
    if ctx.subject.get("rule_version"):
        args["rule_version"] = ctx.subject["rule_version"]
    result = await ctx.tool("get_calculation_schema", args)
    if "error" in result:
        return {"route": "end"}
    if result.get("status") != "approved" or (
        args.get("rule_version") and args["rule_version"] != result.get("rule_version")
    ):
        reason = result.get("reason") or "指定版本的规则尚未发布"
        ctx.emit("error", dict(code="RULE_NOT_PUBLISHED", text=reason, retryable=False))
        ctx.emit(
            "answer",
            dict(text=reason, citations=[], action="block_unreviewed"),
            "completed",
        )
        return {"route": "end"}
    ctx.subject.update(rule_version=result["rule_version"], pending=state["kind"])
    return {"schema": result, "route": "collect"}


def valid(value, field):
    if field.get("type") == "string" or field["name"] == "defect":
        return bool(value)
    try:
        number = Decimal(value)
        return (
            number.is_finite()
            and number >= Decimal(str(field.get("minimum", "-Infinity")))
            and number <= Decimal(str(field.get("maximum", "Infinity")))
            and (
                "enum" not in field
                or number in [Decimal(str(v)) for v in field["enum"]]
            )
        )
    except InvalidOperation:
        return False


async def collect(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context
    q, kind, rule = state["query"], state["kind"], state["schema"]
    sub = ctx.subject
    active = state.get("active_subject_id") or sub.get("subject_id") or "default"
    named = re.search(r"管段\s*([A-Za-z0-9_-]+)", q)
    if named and named.group(1) != active:
        ctx.emit(
            "clarification_required",
            dict(text="请确认要计算的管段。原管段已确认参数不会套用。"),
            "waiting_clarification",
        )
        return {"route": "end", "active_subject_id": active, "pending": ["管段"]}
    slots = sub.setdefault("slots", {}).setdefault(kind, {})
    if sub.setdefault("versions", {}).get(kind) != rule["rule_version"]:
        slots.clear()
        sub.pop("observations", None)
        sub["versions"][kind] = rule["rule_version"]
        kept = sub.pop("prefilled_slots", None)
        if kept:
            slots.update(kept)
    if not slots:
        for item in state.get("confirmed") or []:
            if (
                item.get("subject_id") == active
                and item.get("confirmed")
                and item.get("kind") in (None, kind)
            ):
                slots[item["name"]] = {
                    "value": item.get("value"),
                    "unit": item.get("unit"),
                    "source_turn_id": item.get("source_turn_id"),
                    "confirmed": True,
                }
    recent = [
        dict(item)
        for item in (state.get("recent_values") or sub.get("recent_values") or [])
        if item.get("subject_id") in (None, active)
    ]
    spacing = re.search(r"间距(?:为|是)?\s*(\d+(?:\.\d+)?)(?:\s*(米|m))?", q)
    if spacing and spacing.group(1) and not spacing.group(2):
        ctx.emit(
            "clarification_required",
            dict(text="间距的单位不明，该项不会记入可复用内容。"),
            "waiting_clarification",
        )
        return {"route": "end", "active_subject_id": active, "pending": ["间距"]}
    if spacing and spacing.group(2):
        recent = [
            item for item in recent if item.get("name") != "间距"
        ] + [
            {
                "name": "间距",
                "value": spacing.group(1),
                "unit": "米",
                "subject_id": active,
                "source_turn_id": ctx.turn,
                "confirmed": True,
            }
        ]
    reused_note = ""
    referred = re.search(r"刚才那个\s*(\S+)", q)
    if referred:
        hint = referred.group(1).strip("，,。 ")
        found = [
            item
            for item in recent
            if hint in str(item.get("name")) or str(item.get("name")) in hint
        ]
        if len(found) != 1:
            ctx.emit(
                "clarification_required",
                dict(text="不能确定「刚才那个」指哪一项。"),
                "waiting_clarification",
            )
            return {"route": "end", "active_subject_id": active, "recent_values": recent}
        reused_note = f"沿用{found[0]['name']}={found[0]['value']}{found[0].get('unit') or ''}"
    previous = {
        item["name"]: item.get("value")
        for item in (state.get("confirmed") or [])
        if item.get("subject_id") == active and item.get("kind") in (None, kind)
    }
    sub["recent_values"] = recent
    series = re.search(
        r"([KT])\s*(?:分别)?\s*(?:=|取值?为?|为)\s*(\d+(?:\.\d+)?(?:\s*[,，、]\s*\d+(?:\.\d+)?)+)",
        q,
    )
    if series:
        sub["curve"] = [series[1], re.split(r"\s*[,，、]\s*", series[2])]
    curve = sub.get("curve")
    missing, invalid = [], []
    newly = set()
    fields = rule["fields"]
    implicit = [
        f
        for f in fields
        if (f.get("label_zh") and f["label_zh"] in q)
        or re.search(re.escape(f["name"]) + r"\s*(?:为|是|取)", q)
    ]
    extracted = await extract_slots(q, implicit) if implicit else {}
    alternate = rule.get("alternate_inputs") or {}
    facts = {}
    if alternate:
        raw_slots = sub.setdefault("observations", {})
        for key, value in observations(q, alternate).items():
            raw_slots[key] = dict(
                value=value, source_turn_id=ctx.turn, confirmed_at=now()
            )
        facts = {key: record["value"] for key, record in raw_slots.items()}
        if "defects" in facts and "gap_m" in facts:
            defect = facts["defects"][0]
            checked = await ctx.tool(
                "lookup_defect_score",
                dict(
                    defect=defect["defect"],
                    grade=defect["grade"],
                    rule_version=rule["rule_version"],
                ),
            )
            if "error" in checked:
                return {"route": "end"}
            if "score" in defect and Decimal(defect["score"]) != Decimal(
                str(checked["row"]["score"])
            ):
                ctx.emit(
                    "error",
                    dict(
                        code="INVALID_PARAMETER",
                        text="题给分值与已审核缺陷分值表不一致。",
                        row=checked["row"],
                    ),
                    "waiting_clarification",
                )
                return {"route": "end"}
    for field in rule["fields"]:
        key = field["name"]
        if curve and key == curve[0]:
            if not all(valid(v, field) for v in curve[1]):
                invalid.append(key)
            if series or not re.search(re.escape(key) + r"\s*[=:：]", q):
                continue
        pattern = (
            r"(?<![A-Za-z])" + re.escape(key) + r"\s*[=:：]\s*([^\s,，、。；;（）()]+)"
        )
        found_values = re.findall(pattern, q)
        if len(set(found_values)) > 1:
            ctx.emit(
                "clarification_required",
                dict(text=f"{key} 的取值冲突，确认前不计算。"),
                "waiting_clarification",
            )
            return {
                "route": "end",
                "active_subject_id": active,
                "pending": [key],
                "recent_values": recent,
                "confirmed": _confirmed_rows(slots, active, kind, ctx.turn),
            }
        match = found_values[0] if found_values else None
        value = match if match is not None else extracted.get(key)
        if value is not None:
            newly.add(key)
            if not valid(value, field):
                invalid.append(key)
                slots.pop(key, None)
            else:
                slots[key] = dict(
                    value=value,
                    unit=field.get("unit"),
                    source_turn_id=ctx.turn,
                    confirmed=True,
                    confirmed_at=now(),
                )
        if key not in slots:
            if key == "F" and "defects" in facts and "gap_m" in facts:
                continue
            if key == "E" and "D" in facts:
                continue
            if key == "T" and facts.get("soil") in alternate.get("soil_columns", []):
                continue
            missing.append(field)
    denied = set()
    for match in re.finditer(
        r"(?:不是|不对|别用).{0,8}([A-Za-z]+|间距)|([A-Za-z]+|间距).{0,6}(?:不是|不对|别用)",
        q,
    ):
        denied.add(next(group for group in match.groups() if group))
    if denied & set(slots):
        for name in denied & set(slots):
            slots.pop(name, None)
        ctx.emit(
            "clarification_required",
            dict(text="被否定的旧参数在确认更新前不进入计算。"),
            "waiting_clarification",
        )
        return {
            "route": "end",
            "active_subject_id": active,
            "pending": sorted(denied),
            "recent_values": recent,
            "confirmed": _confirmed_rows(slots, active, kind, ctx.turn),
        }
    values = {k: v["value"] for k, v in slots.items()}
    if alternate:
        soil = facts.get("soil")
        if soil and soil not in alternate["soil_columns"] and "T" not in values:
            field = next(f for f in fields if f["name"] == "T")
            if field not in missing and not (
                curve and ctx.subject.get("continuing") and series
            ):
                missing.append(field)
            if field in missing:
                missing[missing.index(field)] = dict(
                    field,
                    description="请确认原表土质列，或直接给出 T。可选："
                    + "、".join(alternate["soil_columns"]),
                )
        if curve and soil is not None and not ctx.subject.get("continuing"):
            sub["compare_base"] = True
        if "T" in values or (curve and soil not in alternate["soil_columns"]):
            facts.pop("soil", None)
        values.update(facts)
    sub["missing"] = missing
    confirmed = _confirmed_rows(slots, active, kind, ctx.turn)
    reused = {
        key: value
        for key, value in values.items()
        if key not in newly and key in previous and previous[key] == value
    }
    short_term = {
        "active_subject_id": active,
        "confirmed": confirmed,
        "pending": [
            field["name"] if isinstance(field, dict) else field for field in missing
        ],
        "recent_values": recent,
        "reused": reused,
        "reused_note": reused_note,
    }
    if invalid:
        ctx.emit(
            "error",
            dict(
                code="INVALID_PARAMETER",
                text="请按字段范围重新填写 " + "、".join(invalid),
                retryable=False,
            ),
            "waiting_clarification",
        )
        return {"route": "end", **short_term}
    if missing:
        alternatives = (
            {"F": ["F", "defects"], "E": ["E", "D"], "T": ["T", "soil"]}
            if kind == "RI"
            else {}
        )
        groups = [
            dict(
                id="_or_".join(alternatives.get(f["name"], [f["name"]])),
                any_of=alternatives.get(f["name"], [f["name"]]),
                label_zh=f.get("label_zh", f["name"]),
            )
            for f in missing
        ]
        ctx.emit(
            "clarification_required",
            dict(
                fields=missing,
                groups=groups,
                confirmed={k: v["value"] for k, v in slots.items()},
                missing_parameter_groups=groups,
            ),
            "waiting_clarification",
        )
        return {"route": "end", **short_term}
    return dict(values=values, route="calculate", **short_term)


async def calculate(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context
    kind, version = state["kind"], state["schema"]["rule_version"]
    curve = ctx.subject.get("curve")
    inputs = (
        [state["values"] | {curve[0]: v} for v in curve[1]]
        if curve
        else [state["values"]]
    )
    compare_base = bool(
        curve
        and ctx.subject.get("compare_base")
        and ("T" in state["values"] or "soil" in state["values"])
    )
    if curve:
        for point in inputs:
            if curve[0] == "T":
                point.pop("soil", None)
    if compare_base:
        inputs.insert(0, state["values"])
    ids = []
    for index, values in enumerate(inputs):
        args = dict(calculation_type=kind, rule_version=version, parameters=values)
        digest = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        if kind == "defect_score":
            output = await ctx.tool(
                "lookup_defect_score", dict(values, rule_version=version)
            )
        else:
            output = await ctx.tool(
                "calculate_index", dict(args, idempotency_key=digest)
            )
        if "error" in output:
            return {"route": "end"}
        if compare_base and index == 0:
            ctx.emit("answer", output)
        elif curve:
            ids.append(output["result_id"])
        else:
            ctx.subject["pending"] = None
            if state.get("reused") or state.get("reused_note"):
                output = dict(output)
                note = []
                if state.get("reused"):
                    output["reused"] = state["reused"]
                    note.append(
                        "沿用"
                        + "、".join(f"{k}={v}" for k, v in state["reused"].items())
                    )
                if state.get("reused_note"):
                    note.append(state["reused_note"])
                output["text"] = "。".join(note)
            ctx.emit("answer", output, "completed")
    return dict(ids=ids, route="plot" if curve else "end")


async def plot(state: State, runtime: Runtime[Turn]):
    ctx = runtime.context
    axis = ctx.subject["curve"][0]
    args = dict(
        result_ids=state["ids"],
        x_axis=axis,
        y_axis=state["kind"],
        rule_version=state["schema"]["rule_version"],
        fixed_parameters_summary="，".join(
            f"{k}={v}" for k, v in state["values"].items() if k != axis
        ),
    )
    chart = await ctx.tool("plot_curve", args)
    if "error" not in chart:
        ctx.emit("chart", {"resource_id": chart["resource_id"]})
        ctx.subject.update(pending=None, curve=None)
        ctx.emit(
            "answer",
            dict(
                text="曲线已生成。",
                result_ids=state["ids"],
                resource_id=chart["resource_id"],
            ),
            "completed",
        )
    return {}


def compile_graph(checkpointer=None, store=None):
    builder = StateGraph(State, context_schema=Turn)

    def checkpointed(node):
        async def execute(state: State, runtime: Runtime[Turn]):
            update = await node(state, runtime) or {}
            next_node = "verify" if node is retrieve else update.get("route", "end")
            update = dict(update)
            update["resume_at"] = "plan" if next_node == "end" else next_node
            return update

        return execute

    def enter(state: State):
        target = state.get("resume_at") or "plan"
        return "plan" if target == "end" else target

    nodes = (plan, retrieve, verify, answer, schema, collect, calculate, plot)
    for node in nodes:
        builder.add_node(node.__name__, checkpointed(node))
    builder.add_conditional_edges(
        START,
        enter,
        {node.__name__: node.__name__ for node in nodes} | {"end": END},
    )
    for name, targets in {
        "plan": ["retrieve", "schema", "end"],
        "verify": ["answer", "end"],
        "answer": ["schema", "end"],
        "schema": ["collect", "end"],
        "collect": ["calculate", "end"],
        "calculate": ["plot", "end"],
    }.items():
        builder.add_conditional_edges(
            name,
            lambda state: state["route"],
            {t: END if t == "end" else t for t in targets},
        )
    builder.add_edge("retrieve", "verify")
    builder.add_edge("plot", END)
    return builder.compile(checkpointer=checkpointer, store=store)


workflow = compile_graph()
_graph = None


def get_graph():
    return _graph or workflow


def set_graph(compiled):
    global _graph
    _graph = compiled
