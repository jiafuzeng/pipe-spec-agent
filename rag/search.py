"""Retrieve only the version selected by the approval registry."""

import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import httpx

from rag.pipeline import client, model


def terms(text):
    tokens = re.findall(r"[a-z0-9.]+|[\u3400-\u9fff]", text.lower())
    for phrase in re.findall(r"[\u3400-\u9fff]{2,}", text):
        tokens.extend(phrase[i:i + 2] for i in range(len(phrase) - 1))
    return tokens


def lexical_query_terms(query):
    # Abbreviations in CJJ 181 section 2.1; preserve original terms as well.
    expanded = re.sub(r"(?i)\b(cctv|qv)\b", lambda m: m[0] + " " + {
        "cctv": "电视检测", "qv": "管道潜望镜检测"
    }[m[0].lower()], query, flags=re.ASCII)
    return terms(expanded)


def clause_mentioned(clause, query):
    return bool(re.search(r"(?<![\d.])" + re.escape(clause) + r"(?![\d.-])",
                          re.sub(r"表\s+", "表", query)))


CLAUSE_HEADING = re.compile(
    r"(?m)^[ \t#>]*(?:续(?=表))?(表[ \t]*)?(\d+\.\d+\.\d+(?:-\d+)?)(?=[ \t]|$)"
)


def citation_spans(text, clause, page):
    """Attach a clause only to the contiguous text under its heading in this chunk."""
    spans = []
    start = 0
    for heading in CLAUSE_HEADING.finditer(text):
        prefix = text[start:heading.start()].strip()
        if prefix and clause:
            spans.append(dict(clause=clause, page=page, quote=prefix))
        clause = ("表" if heading[1] else "") + heading[2]
        start = heading.start()
    tail = text[start:].strip()
    if tail and clause:
        spans.append(dict(clause=clause, page=page, quote=tail))
    return spans


class RemoteReranker:
    def __init__(self, base_url, name, key):
        self.endpoint = base_url.rstrip("/") + "/rerank"
        self.name = name
        self.http = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=30)

    def predict(self, pairs):
        if not pairs:
            return []
        query = pairs[0][0]
        documents = [document for _, document in pairs]
        try:
            response = self.http.post(self.endpoint, json={
                "model": self.name, "query": query, "documents": documents,
                "top_n": len(documents), "return_documents": False,
            })
        except httpx.RequestError:
            raise RuntimeError("重排服务连接失败") from None
        if not response.is_success:
            raise RuntimeError(f"重排请求失败（HTTP {response.status_code}）")
        payload = response.json()
        rows = payload.get("results", payload.get("data"))
        if not isinstance(rows, list) or len(rows) != len(documents):
            raise ValueError("重排接口未返回全部候选")
        scores = [None] * len(documents)
        for row in rows:
            index = row["index"]
            score = row["relevance_score"]
            if type(index) is not int or not 0 <= index < len(scores) or scores[index] is not None:
                raise ValueError("重排接口返回无效候选序号")
            if type(score) not in (int, float) or not math.isfinite(score):
                raise ValueError("重排接口返回无效分数")
            scores[index] = score
        return scores


@lru_cache(maxsize=1)
def reranker():
    if base_url := os.getenv("RERANKER_BASE_URL"):
        key = os.getenv("RERANKER_API_KEY")
        if not key:
            raise ValueError("未配置 RERANKER_API_KEY")
        return RemoteReranker(base_url, os.getenv("RERANKER_MODEL", "qwen3-rerank"), key)
    from sentence_transformers import CrossEncoder

    return CrossEncoder(os.environ["RERANKER_MODEL"])


def search(root, registry, query, limit=5):
    return search_indexes(root, registry.active(), query, limit, review_status="approved")


def search_indexes(root, indexes, query, limit, *, review_status):
    from rank_bm25 import BM25Okapi

    candidates = {}
    for row in indexes:
        config = json.loads(row["config"])
        provider = config["embedding_profile_id"].split(":")[0]
        if config["embedding_model_version"] != os.getenv(
            provider.upper() + "_MODEL_VERSION", "v1"
        ):
            raise ValueError("索引模型版本与查询配置不一致，请重建索引")
        collection = client(root).get_collection(row["id"])

        def semantic():
            vec = model(config["embedding_profile_id"]).get_query_embedding(query)
            return collection.query(
                query_embeddings=[vec],
                where={"review_status": review_status},
                n_results=min(row["count"], 20),
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(semantic)
            corpus = collection.get(where={"review_status": review_status})
            scores = BM25Okapi([terms(t) for t in corpus["documents"]]).get_scores(
                lexical_query_terms(query)
            )
            hits = future.result()
        vector = dict(zip(hits["ids"][0], hits["distances"][0]))
        best = set(
            sorted(range(len(scores)), key=scores.__getitem__, reverse=True)[:20]
        )
        for i, (key, text, meta) in enumerate(
            zip(corpus["ids"], corpus["documents"], corpus["metadatas"])
        ):
            clause = meta.get("clause_no")
            if not clause:
                continue
            spans = citation_spans(text, clause, meta.get("page_pdf"))
            exact = any(
                clause_mentioned(span["clause"], query)
                for span in spans
            )
            if i in best or key in vector or exact:
                candidates[key] = dict(
                    evidence_id=key,
                    quote=text,
                    citation_spans=spans,
                    clause_no=clause,
                    exact=exact,
                    bm25_score=float(scores[i]),
                    vector_distance=vector.get(key),
                    retrieval_sources=[
                        source
                        for source, selected in [
                            ("bm25", i in best),
                            ("vector", key in vector),
                            ("exact", exact),
                        ]
                        if selected
                    ],
                    chapter=meta.get("section_path"),
                    content_type=meta.get("content_type"),
                    docmind_layout_ids=meta.get("docmind_layout_ids"),
                    page_pdf=meta.get("page_pdf"),
                    page_printed=None,
                    source_hash=row["source"],
                    review_status=review_status,
                    job_id=row["id"],
                )
    results = list(candidates.values())
    if results:
        scores = reranker().predict([(query, r["quote"]) for r in results])
        for r, score in zip(results, scores):
            r["reranker_score"] = float(score)
    return sorted(
        results, key=lambda r: (r["exact"], r["reranker_score"]), reverse=True
    )[:limit]
