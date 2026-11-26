"""Retrieve only the version selected by the approval registry."""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from rag.pipeline import client, model


def terms(text):
    return re.findall(r"[a-z0-9.]+|[\u3400-\u9fff]", text.lower())


@lru_cache(maxsize=1)
def reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(os.environ["RERANKER_MODEL"])


def search(root, registry, query, limit=5):
    from rank_bm25 import BM25Okapi

    candidates = {}
    for row in registry.active():
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
                where={"review_status": "approved"},
                n_results=min(row["count"], 20),
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(semantic)
            corpus = collection.get(where={"review_status": "approved"})
            scores = BM25Okapi([terms(t) for t in corpus["documents"]]).get_scores(
                terms(query)
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
            exact = bool(
                re.search(r"(?<![\d.])" + re.escape(clause) + r"(?![\d.-])", query)
            )
            if i in best or key in vector or exact:
                candidates[key] = dict(
                    evidence_id=key,
                    quote=text,
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
                    review_status="approved",
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
