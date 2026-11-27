import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
_report_lock = threading.Lock()


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


@router.get("/api/v1/evaluations/agent")
def agent_eval_report():
    path = Path(__file__).resolve().parents[3] / "agentEval" / "last_report.json"
    if not path.is_file():
        raise HTTPException(
            404, "暂无 agentEval 报告，请先运行 python -m agentEval.run"
        )
    return FileResponse(
        path, media_type="application/json", headers={"Cache-Control": "no-store"}
    )
