"""意图识别 + 问题改写 + create_agent 检索 + 回答校验。"""

from langgraph.errors import GraphRecursionError

from app.agent.answers import REFUSAL, classify_turn, grounded_summary
from app.agent.language import recognize_intent, rewrite_query
from app.agent.prompts import CHITCHAT_REPLY, INTENT_LABEL
from app.agent.state import State
from app.agent.tools import (
    bind_evidence,
    bind_stream_writer,
    emit,
    reset_evidence,
    reset_stream_writer,
)
from app.agent.utils.agent import build_search_agent, react_recursion_limit
from app.agent.utils.messages import last_ai_text
from app.agent.utils.progress import emit_agent_progress
from app.agent.utils.reply import (
    emit_draft_ready,
    emit_final_answer,
    emit_partial_answer,
)
from app.agent.utils.validate import validate_answer


def _is_timeout(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if "timeout" in type(cur).__name__.lower():
            return True
        cur = cur.__cause__ or cur.__context__
    return False


async def node_recognize(state: State):
    """先规则判意图；仅规则落成 qa 时再用 LLM。需检索则进入改写。"""
    q = state["query"]
    intent = classify_turn(q)
    if intent == "qa":
        proposal = await recognize_intent(q)
        if proposal:
            intent = proposal
    label = INTENT_LABEL.get(intent, intent)
    emit(
        "plan_step",
        dict(text=f"意图识别：{label}（{intent}）", intent=intent),
    )
    if intent == "chitchat":
        emit(
            "answer",
            dict(
                text=CHITCHAT_REPLY,
                format="markdown",
                citations=[],
                partial=False,
            ),
            status="completed",
        )
        return dict(intent=intent, query=q, route="end")
    return dict(intent=intent, query=q, evidence=[], route="rewrite")


async def node_rewrite(state: State):
    """将原问题改写为检索查询，再进入 ReAct。"""
    q = state["query"]
    intent = state.get("intent") or "qa"
    search_query = await rewrite_query(q, intent) or q
    emit(
        "plan_step",
        dict(
            text="问题改写为检索查询",
            intent=intent,
            original=q,
            search_query=search_query,
            questions=[search_query],
        ),
    )
    return dict(search_query=search_query, route="react")


async def node_react(state: State):
    """create_agent 检索并生成草稿，交给校验节点定稿。"""
    q = state["query"]
    search_query = state.get("search_query") or q
    intent = state.get("intent") or "qa"
    label = INTENT_LABEL.get(intent, intent)
    collected: list[dict] = []
    writer_token = bind_stream_writer()
    token = bind_evidence(collected)
    try:
        emit(
            "plan_step",
            dict(
                text=f"ReAct：启动检索智能体（意图 {label}，查询「{search_query}」）",
                intent=intent,
            ),
        )
        agent = build_search_agent(
            intent=intent, label=label, search_query=search_query
        )
        text = ""
        try:
            async for mode, chunk in agent.astream(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"用户问：{q}\n"
                                f"检索查询：{search_query}\n"
                                "请按标准结构作答：开场直答，再只分用户问到的方面；"
                                "检索最多 2 次，有条款就停手作答。"
                            ),
                        }
                    ]
                },
                {"recursion_limit": react_recursion_limit()},
                stream_mode=["updates", "values"],
            ):
                if mode == "updates" and isinstance(chunk, dict):
                    emit_agent_progress(chunk)
                elif mode == "values" and isinstance(chunk, dict):
                    text = last_ai_text(chunk.get("messages"))
                    if text:
                        emit_partial_answer(text, collected)
        except GraphRecursionError:
            emit(
                "plan_step",
                dict(text="ReAct：达到步数上限，改用已检索条款整理"),
            )
        except Exception as exc:
            if not _is_timeout(exc):
                raise
            emit(
                "plan_step",
                dict(text="ReAct：模型超时，改用已检索条款整理"),
            )
        draft = text or grounded_summary(collected) or REFUSAL
        emit_draft_ready(draft, collected)
        return dict(
            draft_answer=draft,
            evidence=collected,
            route="validate",
        )
    finally:
        reset_evidence(token)
        reset_stream_writer(writer_token)


async def node_validate(state: State):
    """校验草稿是否紧扣问题，裁掉跑题要点与无关证据后定稿。"""
    q = state["query"]
    draft = state.get("draft_answer") or REFUSAL
    evidence = list(state.get("evidence") or [])
    emit("plan_step", dict(text="回答校验：对照问题裁剪要点与引用"))
    text, kept, dropped = await validate_answer(q, draft, evidence)
    note = ""
    if dropped:
        note = "已去掉：" + "；".join(dropped[:3])
    elif len(kept) < len(evidence):
        note = f"引用 {len(evidence)}→{len(kept)} 条"
    return emit_final_answer(text, kept, note=note)
