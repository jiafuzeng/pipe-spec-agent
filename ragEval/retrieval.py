"""按验证集逐题评估 Top 5 检索结果，输出 JSON 评分报告。"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from statistics import mean
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge.registry import Registry, knowledge_root
from app.rag.retrieval import citation_spans, lexical_query_terms, search, search_indexes, terms


def compact(value):
    return re.sub(r"\s+", "", value or "")


def offline_retriever(root, job, hashes):
    with sqlite3.connect((root / "registry.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT source FROM jobs WHERE id=?", (job,)).fetchone()
        if not row or row[0] not in hashes:
            raise ValueError("所选任务与测试集来源不匹配")
        chunks = db.execute(
            "SELECT node_id,text,metadata FROM chunks WHERE job=? ORDER BY chunk_index", (job,)
        ).fetchall()
    if not chunks:
        raise ValueError("任务没有切片")
    corpus = [
        dict(evidence_id=key, quote=text, source_hash=row[0], **{
            k: meta.get(k) for k in ("clause_no", "page_pdf")
        })
        for key, text, metadata in chunks for meta in [json.loads(metadata)]
    ]
    for item in corpus:
        item["citation_spans"] = citation_spans(item["quote"], item["clause_no"], item["page_pdf"])
    index = BM25Okapi([terms(item["quote"]) for item in corpus])

    def retrieve(query):
        scores = index.get_scores(lexical_query_terms(query))
        # Mirror the lexical candidate cutoff and missing-clause filter in app.rag.retrieval.
        ordered = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)[:20]
        return [corpus[i] for i in ordered if corpus[i]["clause_no"]][:5]

    return retrieve


def evaluate(case, hits, hashes):
    matches = []
    for gold in case["evidence"]:
        ranks = [
            (rank, hit) for rank, hit in enumerate(hits, 1)
            if hit["source_hash"] in hashes and compact(gold["quote"]) in compact(hit["quote"])
        ]
        citation = next((rank for rank, hit in ranks if any(
            compact(span["clause"]) == compact(gold["clause"])
            and span["page"] == gold["page_pdf"]
            and compact(gold["quote"]) in compact(span["quote"])
            for span in hit["citation_spans"]
        )), None)
        matches.append(dict(quote=gold["quote"], clause=gold["clause"], page_pdf=gold["page_pdf"], rank=ranks[0][0] if ranks else None,
                            citation_rank=citation))
    count = len(matches)
    evidence_count = sum(m["rank"] is not None for m in matches)
    citation_count = sum(m["citation_rank"] is not None for m in matches)
    return dict(id=case["id"], query=case["query"], expected_evidence_count=count,
                evidence_score=round(100 * evidence_count / count, 2) if count else None,
                score=round(100 * citation_count / count, 2) if count else None,
                matches=matches, top5=[
        dict(id=h["evidence_id"], clause=h["clause_no"], page=h["page_pdf"], quote=h["quote"],
             citation_spans=h["citation_spans"], retrieval_sources=h.get("retrieval_sources", ["bm25"]), reranker_score=h.get("reranker_score")) for h in hits
    ])


class EvalError(ValueError):
    pass


def dataset_path(dataset=None):
    aliases = {"validation": "rag_validation.json", "baseline": "retrieval_cases.json"}
    if dataset and dataset not in aliases:
        path = Path(dataset)
    else:
        path = Path(__file__).with_name(aliases[dataset or "validation"])
    if not path.is_file():
        raise EvalError(f"验证集不存在：{path}")
    return path


def _usable_job(registry, hashes, job_id=None):
    states = {"built_pending_review", "active_approved", "superseded"}
    jobs = [j for j in registry.jobs() if j["state"] in states and j["source"] in hashes]
    if job_id:
        job = next((j for j in registry.jobs() if j["id"] == job_id), None)
        if not job or job["state"] not in states:
            raise EvalError("请选择已经完成构建的索引")
        if job["source"] not in hashes:
            raise EvalError("索引与验证集来源不一致")
        return job
    active = [j for j in jobs if j["state"] == "active_approved"]
    if active:
        return active[0]
    if jobs:
        return jobs[0]
    raise EvalError("没有可评测的索引，请先导入并构建规程")


def build_report(mode, *, dataset=None, job_id=None, automatic=False):
    """Score the validation set. mode is ``bm25`` or ``hybrid``."""
    if mode not in {"bm25", "hybrid"}:
        raise EvalError("未知评测方式")
    load_dotenv()
    path = dataset_path(dataset)
    data = json.loads(path.read_text(encoding="utf-8"))
    root = knowledge_root()
    registry = Registry(root)
    hashes = data["source_sha256"]
    active = [row["id"] for row in registry.active()]
    evaluated = job_id
    if mode == "bm25":
        job = _usable_job(registry, hashes, job_id) if automatic or job_id else None
        if job is None:
            raise EvalError("请指定已构建索引")
        evaluated = job["id"]
        label = "offline_bm25"
        retrieve = offline_retriever(root, evaluated, hashes)
        reranker = None
    else:
        if not os.getenv("RERANKER_MODEL") and not os.getenv("RERANKER_BASE_URL"):
            raise EvalError("请设置 RERANKER_MODEL 或配置远程重排服务")
        reranker = os.getenv("RERANKER_MODEL", "qwen3-rerank")
        published = [row["id"] for row in registry.active() if row["source"] in hashes]
        if job_id or (automatic and not published):
            job = _usable_job(registry, hashes, job_id)
            evaluated = job["id"]
            status = "pending_review" if job["state"] == "built_pending_review" else "approved"
            label = "offline_hybrid"

            def retrieve(query, job=job, status=status):
                return search_indexes(root, [job], query, 5, review_status=status)
        else:
            if not active:
                raise EvalError("没有已发布索引；可用 --hybrid-job 对指定索引做离线混合评测")
            label = "production"

            def retrieve(query):
                return search(root, registry, query, limit=5)
    results = [evaluate(c, retrieve(c["query"]), hashes) for c in data["cases"]]
    positive = [r["matches"] for r in results if r["matches"]]
    ranks = [[m["rank"] for m in group if m["rank"]] for group in positive]
    summary = {
        "answerable": len(positive),
        "hit_at_5": mean(bool(r) for r in ranks) if positive else None,
        "macro_recall_at_5": mean(len(r) / len(g) for r, g in zip(ranks, positive)) if positive else None,
        "mrr_at_5": mean(1 / min(r) if r else 0 for r in ranks) if positive else None,
        "all_evidence_at_5": sum(len(r) == len(g) for r, g in zip(ranks, positive)),
        "all_citations_at_5": sum(all(m["citation_rank"] for m in g) for g in positive),
        "negative_queries_with_candidates": sum(bool(r["top5"]) for r in results if not r["matches"]),
    }
    return dict(
        mode=label,
        dataset=path.name,
        reranker_model=reranker,
        scoring="evidence_score 为 Top 5 正文证据覆盖率（百分制）；score 另要求条款/表号及 PDF 页序同时正确。库外题两项均为 null。",
        active_jobs=active,
        evaluated_job=evaluated,
        summary=summary,
        results=results,
    )


def write_report(report, output: Path):
    text = json.dumps(report, ensure_ascii=False, indent=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=output.parent, delete=False, encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(f.name, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    jobs = parser.add_mutually_exclusive_group()
    jobs.add_argument("--hybrid-job", help="对指定已构建索引运行多路召回和相关性重排")
    parser.add_argument("--output", type=Path, help="成功后写入完整 JSON 报告")
    jobs.add_argument("--bm25-job", help="对指定任务的现有切片做离线 BM25 对照")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("input_file", nargs="?", help="验证集 JSON 路径")
    inputs.add_argument("--dataset", help="验证集路径，兼容 validation 和 baseline 别名")
    args = parser.parse_args()
    try:
        report = build_report(
            "bm25" if args.bm25_job else "hybrid",
            dataset=args.input_file or args.dataset,
            job_id=args.bm25_job or args.hybrid_job,
        )
    except EvalError as exc:
        parser.error(str(exc))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        write_report(report, args.output)
    else:
        print(text)


if __name__ == "__main__":
    main()
