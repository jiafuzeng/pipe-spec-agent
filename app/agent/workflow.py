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
    search_evidence,
)
from app.agent.utils.agent import build_search_agent, react_recursion_limit
from app.agent.utils.messages import last_ai_text
from app.agent.utils.progress import emit_agent_progress
from app.agent.utils.reply import (
    emit_draft_ready,
    emit_final_answer,
    emit_partial_answer,
)
from log import trace


def _is_timeout(exc: BaseException) -> bool:
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if "timeout" in type(cur).__name__.lower():
            return True
        if cur.__cause__ is not None:
            stack.append(cur.__cause__)
        if cur.__context__ is not None:
            stack.append(cur.__context__)
        if isinstance(cur, BaseExceptionGroup):
            stack.extend(cur.exceptions)
    return False


async def node_recognize(state: State):
    """先规则判意图；仅规则落成 retrieve 时再用 LLM。需检索则进入改写。"""
    q = state["query"]
    intent = classify_turn(q)
    if intent == "retrieve":
        proposal = await recognize_intent(q)
        if proposal:
            intent = proposal
    label = INTENT_LABEL.get(intent, intent)
    trace("recognize", intent=intent, query=q)
    emit(
        "plan_step",
        dict(
            text=f"意图识别：{label}",
            intent=intent,
            intent_label=label,
        ),
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
    intent = state.get("intent") or "retrieve"
    search_query = await rewrite_query(q, intent) or q
    trace("rewrite.node", search_query=search_query)
    emit(
        "plan_step",
        dict(
            text="问题改写为检索查询",
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
    intent = state.get("intent") or "retrieve"
    label = INTENT_LABEL.get(intent, intent)
    collected: list[dict] = []
    writer_token = bind_stream_writer()
    token = bind_evidence(collected)
    try:
        trace("react.start", intent=intent, search_query=search_query)
        emit(
            "plan_step",
            dict(
                text=f"ReAct：启动检索智能体（意图 {label}，查询「{search_query}」）",
            ),
        )
        agent = build_search_agent(
            intent=intent, label=label, search_query=search_query
        )
        text = ""
        recovered = False
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
            recovered = True
            trace("react.limit", evidence=len(collected))
            emit(
                "plan_step",
                dict(text="ReAct：达到步数上限，改用已检索条款整理"),
            )
        except Exception as exc:
            if not _is_timeout(exc):
                trace("react.error", error=type(exc).__name__)
                raise
            recovered = True
            trace("react.timeout", error=type(exc).__name__, evidence=len(collected))
            emit(
                "plan_step",
                dict(text="ReAct：模型超时，改用已检索条款整理"),
            )
        if recovered and not collected:
            items, _ = await search_evidence(search_query)
            collected.extend(items)
            for item in items:
                emit("evidence", item)
            trace("react.recover_search", hits=len(items))
        draft = text or grounded_summary(collected) or REFUSAL
        trace("react.done", evidence=len(collected), draft=len(draft or ""))
        emit_draft_ready(draft, collected)
        return emit_final_answer(draft, collected)
    finally:
        reset_evidence(token)
        reset_stream_writer(writer_token)


async def node_validate(state: State):
    """定稿已在 react 发出；此节点只做收尾，不再阻塞 SSE。"""
    draft = state.get("draft_answer") or REFUSAL
    evidence = list(state.get("evidence") or [])
    return emit_final_answer(draft, evidence)
