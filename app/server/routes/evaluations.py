import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
_report_lock = threading.Lock()
_agent_lock = threading.Lock()


def _scores(mode: str) -> Path:
    return Path(__file__).resolve().parents[3] / "ragEval" / f"{mode}_scores.json"


def _ensure_report(mode: str, refresh: bool):
    path = _scores(mode)
    if path.is_file() and not refresh:
        return path
    with _report_lock:
        if path.is_file() and not refresh:
            return path
        from ragEval.retrieval import EvalError, build_report, write_report

        try:
            write_report(build_report(mode, automatic=True), path)
        except EvalError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, f"评测失败：{exc}") from exc
    return path


@router.get("/api/v1/knowledge/rag-eval")
@router.get("/api/v1/evaluations/rag")
def rag_eval(mode: str = "hybrid", refresh: bool = False):
    if mode != "hybrid":
        raise HTTPException(422, "只支持多路召回")
    return FileResponse(
        _ensure_report(mode, refresh),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def _agent_report_path() -> Path:
    return Path(__file__).resolve().parents[3] / "agentEval" / "last_report.json"


def _agent_report(refresh: bool) -> Path:
    path = _agent_report_path()
    if path.is_file() and not refresh:
        return path
    with _agent_lock:
        if path.is_file() and not refresh:
            return path
        from app.agent import graph as ag
        from agentEval.run import run_suite

        previous = ag._graph
        try:
            report = run_suite("ci")
            path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            raise HTTPException(503, f"Agent 评测失败：{exc}") from exc
        finally:
            ag.set_graph(previous)
        if not path.is_file():
            raise HTTPException(503, "Agent 评测未写出报告")
    return path


@router.get("/api/v1/evaluations/agent")
def agent_eval_report(refresh: bool = False):
    return FileResponse(
        _agent_report(refresh),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )
