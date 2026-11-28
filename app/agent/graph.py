"""编译与挂载 LangGraph 工作流。"""

from langgraph.graph import END, START, StateGraph

from app.agent.state import State, route
from app.agent.workflow import (
    node_react,
    node_recognize,
    node_rewrite,
    node_validate,
)

_graph = None


def compile_graph(checkpointer=None, store=None):
    """编译图：START → recognize → rewrite → react → validate → END。"""
    g = StateGraph(State)
    g.add_node("recognize", node_recognize)
    g.add_node("rewrite", node_rewrite)
    g.add_node("react", node_react)
    g.add_node("validate", node_validate)
    g.add_edge(START, "recognize")
    g.add_conditional_edges(
        "recognize", route, {"rewrite": "rewrite", "end": END}
    )
    g.add_edge("rewrite", "react")
    g.add_edge("react", "validate")
    g.add_edge("validate", END)
    return g.compile(checkpointer=checkpointer, store=store)


workflow = compile_graph()


def get_graph():
    return _graph or workflow


def set_graph(compiled):
    global _graph
    _graph = compiled
