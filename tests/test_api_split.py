import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.knowledge.ingestion import client
from app.knowledge.registry import Registry
from rag.web import API, app


class ApiSplitTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_parallel_chroma_open_reuses_one_client(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            def open_once():
                return client(root)

            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = list(pool.map(lambda _: open_once(), (0, 1)))
        self.assertIs(first, second)

    def test_chunk_strategies_are_listed(self):
        body = self.client.get("/api/v1/knowledge/limits").json()
        ids = [item["id"] for item in body["chunk_strategies"]]
        self.assertEqual(
            ids,
            [
                "structure",
                "sentence",
                "token",
                "markdown",
                "sentence_window",
                "hierarchical",
                "semantic",
                "semantic_merge",
            ],
        )

    def test_api_does_not_serve_the_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("text/html", response.headers.get("content-type", ""))

    def test_frontend_origin_can_call_the_api(self):
        origin = "http://127.0.0.1:5173"
        response = self.client.get("/health", headers={"Origin": origin})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], origin)

        preflight = self.client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertIn(preflight.status_code, (200, 204))
        self.assertEqual(preflight.headers["access-control-allow-origin"], origin)

    def test_delete_removes_only_the_selected_file(self):
        from app.server.routes import knowledge as web

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = Registry(root)
            keep, _ = registry.reserve(
                "keep", "v1", {"original_filename": "keep.pdf", "edition": "x"}
            )
            drop, _ = registry.reserve(
                "drop", "v1", {"original_filename": "drop.pdf", "edition": "x"}
            )
            registry.finish(keep, 0)
            registry.finish(drop, 0)
            store = client(root)
            for job in (keep, drop):
                store.create_collection(job).add(
                    ids=[job],
                    embeddings=[[0.1, 0.2, 0.3]],
                    documents=["文本"],
                    metadatas=[{"review_status": "pending_review"}],
                )
            with (
                patch.object(web, "ROOT", root),
                patch.object(web, "db", registry),
            ):
                response = TestClient(app).delete(API + "/documents/drop")
            self.assertEqual(response.status_code, 200, response.text)
            names = {
                item if isinstance(item, str) else item.name
                for item in client(root).list_collections()
            }
            self.assertIn(keep, names)
            self.assertNotIn(drop, names)
            states = {row["id"]: row["state"] for row in registry.jobs()}
            self.assertEqual(states[drop], "deleted")
            self.assertEqual(states[keep], "built_pending_review")
