from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/api/v1/knowledge/rag-eval")
@router.get("/api/v1/evaluations/rag")
def rag_eval(mode: str = "bm25"):
    if mode not in {"bm25", "hybrid"}:
        raise HTTPException(422, "未知评测方式")
    path = Path(__file__).resolve().parents[3] / "ragEval" / f"{mode}_scores.json"
    if not path.is_file():
        raise HTTPException(
            404, f"暂无评测报告，请先运行 ragEval/retrieval.py 生成 {mode}_scores.json"
        )
    return FileResponse(
        path, media_type="application/json", headers={"Cache-Control": "no-store"}
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
