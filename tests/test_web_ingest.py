"""006: real LlamaIndex + persistent Chroma; embedding and remote parser are controlled."""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from llama_index.core.embeddings import MockEmbedding

from main import app
from app.server.routes import knowledge as web
from app.rag.pipeline import client
from app.knowledge.registry import Registry

ROOT = Path(__file__).resolve().parents[1]


class WebIngestionTests(unittest.TestCase):
    def test_pdf_preview_build_restart_and_approve(self):
        pdf = next((ROOT / "docs").glob("*.pdf"))
        layouts = (ROOT / "data/document.json")
        files = {
            "source_file": (pdf.name, pdf.read_bytes()),
            "docmind_json": ("document.json", layouts.read_bytes()),
        }
        embed = MockEmbedding(embed_dim=8)
        with (
            TemporaryDirectory() as tmp,
            patch.object(web, "ROOT", Path(tmp)),
            patch.object(web, "db", Registry(Path(tmp))),
            patch.object(web, "model", return_value=embed) as probe,
            patch("app.rag.pipeline.model", return_value=embed),
        ):
            api = TestClient(app)
            prefix = web.API
            preview = api.post(prefix + "/imports/preview", files=files)
            self.assertEqual(preview.status_code, 200, preview.text[:500])
            probe.assert_not_called()
            body = preview.json()
            self.assertEqual(len(body["chunks"]), body["total"])
            self.assertGreater(body["total"], 10)
            created = api.post(prefix + "/imports", files=files).json()
            job = created["job_id"]
            row = api.get(prefix + "/imports/" + job).json()
            self.assertEqual(row["state"], "built_pending_review", row)
            self.assertEqual(row["count"], preview.json()["total"])
            restored = Registry(Path(tmp))
            self.assertFalse(restored.active())
            collection = client(Path(tmp)).get_collection(job)
            sample = collection.get(where={"chunk_index": 0})
            self.assertEqual(
                sample["documents"][0], preview.json()["chunks"][0]["text"]
            )
            self.assertEqual(sample["metadatas"][0]["page_pdf"], 1)
            self.assertEqual(
                api.post(prefix + "/imports", files=files).json()["job_id"], job
            )
            url = prefix + "/documents/" + created["source_doc_id"]
            response = api.post(
                url + "/approve", params=dict(job_id=job, actor="test", confirmed=True)
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(restored.active()[0]["id"], job)
            from app.rag.retrieval import search

            with (
                patch("app.rag.retrieval.model", return_value=embed),
                patch("app.rag.retrieval.reranker") as rank,
            ):
                rank.return_value.predict.side_effect = lambda pairs: [0.5] * len(pairs)
                hits = search(Path(tmp), restored, "第1.0.1条")
                self.assertEqual(hits[0]["clause_no"], "1.0.1")
                self.assertTrue(
                    all(item["review_status"] == "approved" for item in hits)
                )
            reloaded = subprocess.check_output(
                [
                    sys.executable,
                    "-c",
                    "import chromadb,sys; print(chromadb.PersistentClient(path=sys.argv[1]).get_collection(sys.argv[2]).count())",
                    str(Path(tmp) / "chroma"),
                    job,
                ],
                text=True,
                timeout=30,
            )
            self.assertEqual(int(reloaded.strip()), row["count"])
            api.delete(url)
            self.assertFalse(restored.active())

    def test_ing02_parser_and_ing08_failed_rebuild(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock

        pdf = next((ROOT / "docs").glob("*.pdf"))
        files = {"source_file": (pdf.name, pdf.read_bytes())}

        def parse(source, output, **options):
            output.mkdir(parents=True, exist_ok=True)
            (output / "document.json").write_text(
                '{"Data":{"layouts":[{"text":"1.0.1 测试","pageNum":0}]}}'
            )
            (output / "document.md").write_text("1.0.1 测试")

        parser = Mock(side_effect=parse)
        embed = MockEmbedding(embed_dim=8)
        with (
            TemporaryDirectory() as tmp,
            patch.object(web, "ROOT", Path(tmp)),
            patch.object(web, "db", Registry(Path(tmp))),
            patch.object(web, "model", return_value=embed),
            patch.object(web, "bundled_layouts", return_value=None),
            patch.dict(
                sys.modules, {"docmind_parse": SimpleNamespace(parse_document=parser)}
            ),
        ):
            api = TestClient(app)
            with patch("app.rag.pipeline.model", return_value=embed):
                job = api.post(web.API + "/imports", files=files).json()["job_id"]
            parser.assert_called_once()
            row = web.job_info(job)
            self.assertEqual(row["state"], "built_pending_review")
            self.assertTrue(
                (
                    Path(tmp)
                    / "parsed"
                    / row["source"]
                    / row["version"]
                    / "document.md"
                ).is_file()
            )
            web.approve(row["source"], job, "test", True)
            with patch(
                "app.rag.pipeline.model", side_effect=RuntimeError("private provider error")
            ):
                other = api.post(
                    web.API + "/imports", files=files, data={"chunking.chunk_size": 768}
                ).json()["job_id"]
            self.assertEqual(web.job_info(other)["state"], "failed")
            self.assertNotIn("private provider error", web.job_info(other)["error"])
            self.assertEqual(web.db.active()[0]["id"], job)
