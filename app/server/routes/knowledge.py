import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
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

from app.rag.pipeline import PROFILES, build, client, index_nodes, model
from app.knowledge.registry import Registry, knowledge_root
from app.knowledge.source import (
    EDITION,
    PDF_SHA,
    STRATEGIES,
    bundled_layouts,
    configuration,
)

load_dotenv()
ROOT = knowledge_root()
db = Registry(ROOT)


@asynccontextmanager
async def lifespan(app):
    # The documented deployment uses a single ingestion worker.
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET state='failed',error='服务重启，请重新提交任务' WHERE state IN ('queued','parsing','chunking','embedding')"
        )
    yield


router = APIRouter()
API = "/api/v1/knowledge"
LIMIT = 32 * 1024 * 1024


def health(profile):
    result = dict(
        profile_id=profile,
        provider=profile.split(":")[0],
        model_name=profile.split(":")[1],
        deployment=PROFILES[profile],
        model_version=os.getenv(profile.split(":")[0].upper() + "_MODEL_VERSION", "v1"),
    )
    try:
        dimension = len(model(profile).get_query_embedding("管道"))
        return result | dict(
            available=dimension > 0, dimension=dimension, health_status="connected"
        )
    except Exception:
        if profile == "ollama:bge-m3":
            reason = "请检查后端 OLLAMA_BASE_URL、Ollama 服务及 bge-m3 模型"
        elif not os.getenv("DASHSCOPE_API_KEY"):
            reason = "后端未配置 DASHSCOPE_API_KEY"
        else:
            reason = "请检查 DashScope 服务连接和凭证"
        return result | dict(available=False, dimension=None, health_status=reason)


@router.get(API + "/embedding-profiles")
def profiles():
    return [health(p) for p in PROFILES]


async def payload(file):
    data = await file.read(LIMIT + 1)
    if not 0 < len(data) <= LIMIT:
        raise HTTPException(422, "文件为空或超过 32 MiB")
    return data


def check_pdf(path):
    if len(PdfReader(path).pages) > 500:
        raise ValueError("PDF 超过 500 页")


def save_once(path, data):
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(data)
    try:
        os.link(f.name, path)
    except FileExistsError:
        pass
    finally:
        os.unlink(f.name)


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
    data = await payload(source_file)
    name = Path(source_file.filename or "").name
    ext = Path(name).suffix.lower()
    preview = request.url.path.endswith("/preview")
    sha = hashlib.sha256(data).hexdigest()
    try:
        config = configuration(strategy, size, overlap)
        if embedding_profile_id not in PROFILES or ext not in {".pdf", ".md"}:
            raise ValueError("文件类型或模型未支持")
        if ext == ".pdf" and not data.startswith(b"%PDF-"):
            raise ValueError("无效 PDF")
        if ext == ".md":
            data.decode()
            if b"\x00" in data or docmind_json or docmind_markdown:
                raise ValueError("Markdown 导入格式错误")
        attachments = {}
        if ext == ".pdf" and not docmind_json and not docmind_markdown:
            directory = bundled_layouts(sha)
            if directory:
                attachments.update(
                    {
                        name: (directory / name).read_bytes()
                        for name in ("document.json", "document.md")
                        if (directory / name).is_file()
                    }
                )
        if docmind_json:
            attachments["document.json"] = await payload(docmind_json)
            if not isinstance(
                json.loads(attachments["document.json"]).get("Data", {}).get("layouts"),
                list,
            ):
                raise ValueError("需要 Data.layouts")
        if docmind_markdown:
            attachments["document.md"] = await payload(docmind_markdown)
            attachments["document.md"].decode()
        profile = embedding_profile_id
        version = os.getenv(profile.split(":")[0].upper() + "_MODEL_VERSION", "v1")
        config.update(
            source_doc_id=sha,
            source_hash=sha,
            original_filename=name,
            title=title,
            edition=edition,
            embedding_profile_id=profile,
            embedding_model_version=version,
            review_status="pending_review",
            schema_version=1,
        )
        if not preview:
            status = await run_in_threadpool(health, profile)
            if not status["available"]:
                raise HTTPException(503, status["health_status"])
            config["embedding_dimension"] = status["dimension"]
        signature = {k: hashlib.sha256(v).hexdigest() for k, v in attachments.items()}
        version_id = hashlib.sha256(
            json.dumps([config, signature], sort_keys=True).encode()
        ).hexdigest()
        config["index_version"] = version_id
        with TemporaryDirectory() as tmp:
            root = Path(tmp) if preview else ROOT
            source = root / "originals" / sha / ("source" + ext)
            parsed = root / "parsed" / sha / version_id
            save_once(source, data)
            if ext == ".pdf":
                await run_in_threadpool(check_pdf, source)
            for filename, content in attachments.items():
                save_once(parsed / filename, content)
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
            return dict(job_id=job, source_doc_id=sha, status=job_info(job)["state"])
    except (UnicodeError, ValueError, AttributeError, PdfReadError) as exc:
        message = str(exc).strip() if isinstance(exc, ValueError) else ""
        if not message or len(message) > 80:
            message = "输入无效，请核对文件格式和切片参数"
        raise HTTPException(422, message) from exc


@router.get(API + "/imports/{job_id}")
def job_info(job_id: str):
    for job in db.jobs():
        if job["id"] == job_id:
            return job | {"config": json.loads(job["config"])}
    raise HTTPException(404, "任务不存在")


@router.get(API + "/documents")
def documents():
    return [row | {"config": json.loads(row["config"])} for row in db.jobs()]


def version_for(source, job_id):
    if job_id is None:
        rows = [
            r for r in db.jobs() if r["source"] == source and r["state"] != "deleted"
        ]
        if not rows:
            raise HTTPException(404)
        job_id = next(
            (r["id"] for r in rows if r["state"] == "active_approved"), rows[0]["id"]
        )
    row = job_info(job_id)
    if row["source"] != source or row["state"] == "deleted":
        raise HTTPException(404)
    return row


@router.get(API + "/documents/{source}/original")
def original(source: str, job_id: str):
    row = version_for(source, job_id)
    ext = Path(row["config"]["original_filename"]).suffix.lower()
    return FileResponse(ROOT / "originals" / source / ("source" + ext))


@router.get(API + "/documents/{source}/parsed/{filename}")
def parsed_artifact(source: str, job_id: str, filename: str):
    row = version_for(source, job_id)
    if filename not in {"document.json", "document.md"}:
        raise HTTPException(404)
    file = ROOT / "parsed" / source / row["config"]["index_version"] / filename
    if not file.is_file():
        raise HTTPException(404)
    return FileResponse(file, filename=filename)


@router.get(API + "/documents/{source}/chunks")
def chunks(source: str, job_id: str | None = None, offset: int = 0, limit: int = 10):
    row = version_for(source, job_id)
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422)
    if row["state"] not in {"built_pending_review", "superseded", "active_approved"}:
        raise HTTPException(409, "索引尚未就绪")
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT text,metadata FROM chunks WHERE job=? ORDER BY chunk_index LIMIT ? OFFSET ?",
            (row["id"], limit, offset),
        ).fetchall()
    return [
        dict(
            text=item["text"],
            metadata=json.loads(item["metadata"])
            | {
                "review_status": "approved"
                if row["state"] in {"active_approved", "superseded"}
                else "pending_review"
            },
        )
        for item in rows
    ]


@router.post(API + "/documents/{source}/approve")
def approve(source: str, job_id: str, actor: str, confirmed: bool):
    row = version_for(source, job_id)
    if source != PDF_SHA or row["config"]["edition"] != EDITION or not confirmed:
        raise HTTPException(422, "需对照指定版次原始 PDF 审核")
    if row["state"] != "built_pending_review" or not actor.strip():
        raise HTTPException(409, "请选择待审核版本并填写审核人")
    collection = client(ROOT).get_collection(job_id)
    if collection.count() != row["count"]:
        raise HTTPException(409, "索引数量不一致")
    try:
        # The registry is the final publication switch; partial updates stay invisible.
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
