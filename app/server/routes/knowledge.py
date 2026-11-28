"""知识库导入与审核路由。"""

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from starlette.concurrency import run_in_threadpool

from app.knowledge.ingestion import PROFILES, build, client, index_nodes, model
from app.knowledge.registry import Registry, knowledge_root
from app.knowledge.source import (
    EDITION,
    PDF_SHA,
    STRATEGIES,
    bundled_layouts,
    configuration,
)

ROOT = knowledge_root()
db = Registry(ROOT)
router = APIRouter()
API = "/api/v1/knowledge"
LIMIT = 32 * 1024 * 1024


def health(profile: str):
    base = dict(
        profile_id=profile,
        provider=profile.split(":")[0],
        model_name=profile.split(":")[1],
        deployment=PROFILES[profile],
        model_version=os.getenv(
            profile.split(":")[0].upper() + "_MODEL_VERSION", "v1"
        ),
    )
    try:
        dimension = len(model(profile).get_query_embedding("管道"))
        return base | dict(
            available=dimension > 0, dimension=dimension, health_status="connected"
        )
    except Exception:
        return base | dict(
            available=False, dimension=None, health_status="embedding 不可用"
        )


@router.get(API + "/embedding-profiles")
def profiles():
    return [health(p) for p in PROFILES]


async def _read(file: UploadFile) -> bytes:
    data = await file.read(LIMIT + 1)
    if not 0 < len(data) <= LIMIT:
        raise HTTPException(422, "文件为空或超过 32 MiB")
    return data


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _job(job_id: str):
    for row in db.jobs():
        if row["id"] == job_id:
            return row | {"config": json.loads(row["config"])}
    raise HTTPException(404, "任务不存在")


def _version(source: str, job_id: str | None):
    if job_id is None:
        rows = [
            r for r in db.jobs() if r["source"] == source and r["state"] != "deleted"
        ]
        if not rows:
            raise HTTPException(404)
        job_id = next(
            (r["id"] for r in rows if r["state"] == "active_approved"), rows[0]["id"]
        )
    row = _job(job_id)
    if row["source"] != source or row["state"] == "deleted":
        raise HTTPException(404)
    return row


@router.post(API + "/imports/preview")
@router.post(API + "/imports")
async def submit(
    request: Request,
    background: BackgroundTasks,
    source_file: UploadFile,
    docmind_json: UploadFile | None = None,
    docmind_markdown: UploadFile | None = None,
    title: str = Form("城镇排水管道检测与评估技术规程"),
    edition: str = Form(EDITION),
    strategy: str = Form("structure", alias="chunking.strategy"),
    size: int = Form(512, alias="chunking.chunk_size"),
    overlap: int = Form(64, alias="chunking.chunk_overlap"),
    embedding_profile_id: str = Form("ollama:bge-m3"),
):
    data = await _read(source_file)
    name = Path(source_file.filename or "").name
    ext = Path(name).suffix.lower()
    preview = request.url.path.endswith("/preview")
    sha = hashlib.sha256(data).hexdigest()
    try:
        if embedding_profile_id not in PROFILES or ext not in {".pdf", ".md"}:
            raise ValueError("文件类型或模型未支持")
        if ext == ".pdf" and not data.startswith(b"%PDF-"):
            raise ValueError("无效 PDF")
        if ext == ".md":
            data.decode()
            if b"\x00" in data or docmind_json or docmind_markdown:
                raise ValueError("Markdown 导入格式错误")

        attachments: dict[str, bytes] = {}
        if ext == ".pdf" and not docmind_json and not docmind_markdown:
            directory = bundled_layouts(sha)
            if directory:
                for filename in ("document.json", "document.md"):
                    path = directory / filename
                    if path.is_file():
                        attachments[filename] = path.read_bytes()
        if docmind_json:
            attachments["document.json"] = await _read(docmind_json)
            layouts = (
                json.loads(attachments["document.json"]).get("Data", {}).get("layouts")
            )
            if not isinstance(layouts, list):
                raise ValueError("需要 Data.layouts")
        if docmind_markdown:
            attachments["document.md"] = await _read(docmind_markdown)
            attachments["document.md"].decode()

        config = configuration(strategy, size, overlap)
        config.update(
            source_doc_id=sha,
            source_hash=sha,
            original_filename=name,
            title=title,
            edition=edition,
            embedding_profile_id=embedding_profile_id,
            embedding_model_version=os.getenv(
                embedding_profile_id.split(":")[0].upper() + "_MODEL_VERSION", "v1"
            ),
            review_status="pending_review",
            schema_version=1,
        )
        if not preview:
            status = await run_in_threadpool(health, embedding_profile_id)
            dimension = status["dimension"]
            if not status["available"] or dimension is None:
                raise HTTPException(503, status["health_status"])
            config["embedding_dimension"] = dimension

        signature = {k: hashlib.sha256(v).hexdigest() for k, v in attachments.items()}
        version_id = hashlib.sha256(
            json.dumps([config, signature], sort_keys=True).encode()
        ).hexdigest()
        config["index_version"] = version_id

        with TemporaryDirectory() as tmp:
            root = Path(tmp) if preview else ROOT
            source = root / "originals" / sha / ("source" + ext)
            parsed = root / "parsed" / sha / version_id
            _write(source, data)
            if ext == ".pdf" and len(PdfReader(source).pages) > 500:
                raise ValueError("PDF 超过 500 页")
            for filename, content in attachments.items():
                _write(parsed / filename, content)
            if preview:
                nodes = await run_in_threadpool(index_nodes, source, parsed, config)
                return dict(
                    total=len(nodes),
                    chunks=[dict(text=n.text, metadata=n.metadata) for n in nodes],
                )
            job, created = db.reserve(
                sha, version_id, config, request.headers.get("Idempotency-Key")
            )
            if created:
                background.add_task(build, ROOT, db, job, source, parsed, config)
            return dict(job_id=job, source_doc_id=sha, status=_job(job)["state"])
    except (UnicodeError, ValueError, AttributeError, PdfReadError) as exc:
        message = str(exc).strip() if isinstance(exc, ValueError) else ""
        if not message or len(message) > 80:
            message = "输入无效，请核对文件格式和切片参数"
        raise HTTPException(422, message) from exc


@router.get(API + "/imports/{job_id}")
def job_info(job_id: str):
    return _job(job_id)


@router.get(API + "/documents")
def documents():
    return [row | {"config": json.loads(row["config"])} for row in db.jobs()]


@router.get(API + "/documents/{source}/original")
def original(source: str, job_id: str):
    row = _version(source, job_id)
    ext = Path(row["config"]["original_filename"]).suffix.lower()
    return FileResponse(ROOT / "originals" / source / ("source" + ext))


@router.get(API + "/documents/{source}/parsed/{filename}")
def parsed_artifact(source: str, job_id: str, filename: str):
    row = _version(source, job_id)
    if filename not in {"document.json", "document.md"}:
        raise HTTPException(404)
    file = ROOT / "parsed" / source / row["config"]["index_version"] / filename
    if not file.is_file():
        raise HTTPException(404)
    return FileResponse(file, filename=filename)


@router.get(API + "/documents/{source}/chunks")
def chunks(source: str, job_id: str | None = None, offset: int = 0, limit: int = 10):
    row = _version(source, job_id)
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422)
    if row["state"] not in {"built_pending_review", "superseded", "active_approved"}:
        raise HTTPException(409, "索引尚未就绪")
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT text,metadata FROM chunks WHERE job=? ORDER BY chunk_index LIMIT ? OFFSET ?",
            (row["id"], limit, offset),
        ).fetchall()
    approved = row["state"] in {"active_approved", "superseded"}
    return [
        dict(
            text=item["text"],
            metadata=json.loads(item["metadata"])
            | {"review_status": "approved" if approved else "pending_review"},
        )
        for item in rows
    ]


@router.post(API + "/documents/{source}/approve")
def approve(source: str, job_id: str, actor: str, confirmed: bool):
    row = _version(source, job_id)
    if source != PDF_SHA or row["config"]["edition"] != EDITION or not confirmed:
        raise HTTPException(422, "需对照指定版次原始 PDF 审核")
    if row["state"] != "built_pending_review" or not actor.strip():
        raise HTTPException(409, "请选择待审核版本并填写审核人")
    collection = client(ROOT).get_collection(job_id)
    if collection.count() != row["count"]:
        raise HTTPException(409, "索引数量不一致")
    try:
        for offset in range(0, row["count"], 100):
            batch = collection.get(limit=100, offset=offset, include=[])
            collection.update(
                ids=batch["ids"],
                metadatas=[{"review_status": "approved"} for _ in batch["ids"]],
            )
        db.approve(job_id, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return dict(status="active_approved")


@router.delete(API + "/documents/{source}")
def remove(source: str):
    db.delete(source)
    chroma = client(ROOT)
    present = {c if isinstance(c, str) else c.name for c in chroma.list_collections()}
    for row in db.jobs():
        if row["source"] == source and row["id"] in present:
            chroma.delete_collection(row["id"])
    return dict(status="deleted")


@router.get(API + "/limits")
def limits():
    return {
        "max_file_bytes": LIMIT,
        "max_pdf_pages": 500,
        "chunk_sizes": [256, 512, 768, 1024],
        "chunk_overlaps": [0, 32, 64, 128],
        "chunk_strategies": [{"id": item[0], "label": item[1]} for item in STRATEGIES],
    }
