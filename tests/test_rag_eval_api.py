import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.knowledge.retrieval import RemoteReranker
from app.server.routes import evaluations
from ragEval.retrieval import EvalError


class RagEvalApiTests(unittest.TestCase):
    def test_missing_report_is_generated_and_then_reused(self):
        app = FastAPI()
        app.include_router(evaluations.router)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "hybrid_scores.json"
            with (
                patch.object(evaluations, "_scores", return_value=path),
                patch(
                    "ragEval.retrieval.build_report", return_value={"mode": "production"}
                ) as build,
            ):
                with TestClient(app) as client:
                    first = client.get("/api/v1/evaluations/rag?mode=hybrid")
                    second = client.get("/api/v1/evaluations/rag?mode=hybrid")
                    refreshed = client.get(
                        "/api/v1/evaluations/rag?mode=hybrid&refresh=true"
                    )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json(), {"mode": "production"})
            self.assertEqual(second.json(), first.json())
            self.assertEqual(refreshed.json(), first.json())
            self.assertEqual(build.call_count, 2)
            self.assertEqual(json.loads(path.read_text()), {"mode": "production"})

    def test_missing_index_is_reported(self):
        app = FastAPI()
        app.include_router(evaluations.router)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "hybrid_scores.json"
            with (
                patch.object(evaluations, "_scores", return_value=path),
                patch(
                    "ragEval.retrieval.build_report",
                    side_effect=EvalError("没有可评测的索引，请先导入并构建规程"),
                ),
            ):
                with TestClient(app) as client:
                    response = client.get("/api/v1/evaluations/rag?mode=hybrid")
            self.assertEqual(response.status_code, 409)
            self.assertIn("导入并构建", response.json()["detail"])
            self.assertFalse(path.exists())

    def test_bm25_mode_is_rejected(self):
        app = FastAPI()
        app.include_router(evaluations.router)
        with TestClient(app) as client:
            response = client.get("/api/v1/evaluations/rag?mode=bm25")
        self.assertEqual(response.status_code, 422)
        self.assertIn("多路召回", response.json()["detail"])


class RerankerTests(unittest.TestCase):
    def test_partial_topn_keeps_returned_hits_ahead(self):
        rerank = RemoteReranker("https://example.invalid/v1", "qwen3-rerank", "k")

        class Response:
            is_success = True

            def json(self):
                return {
                    "results": [
                        {"index": 2, "relevance_score": 0.9},
                        {"index": 0, "relevance_score": 0.2},
                    ]
                }

        rerank.http.post = lambda *args, **kwargs: Response()
        scores = rerank.predict([("q", "a"), ("q", "b"), ("q", "c")])
        self.assertEqual(scores[2], 0.9)
        self.assertLess(scores[1], min(scores[0], scores[2]))
