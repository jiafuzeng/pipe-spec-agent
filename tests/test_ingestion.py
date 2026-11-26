import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rag.source import PDF_SHA, sections, configuration
from rag.registry import Registry

ROOT = Path(__file__).resolve().parents[1]


class IngestionTests(unittest.TestCase):
    def test_ing01_real_source(self):
        pdf = next((ROOT / "docs").glob("*.pdf"))
        self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), PDF_SHA)
        parsed = json.loads(
            next((ROOT / "data/docmind").rglob("document.json")).read_bytes()
        )
        items = list(sections(parsed))
        self.assertEqual(items[0][1]["page_pdf"], 1)
        self.assertEqual(
            items[0][1]["docmind_layout_ids"], parsed["Data"]["layouts"][0]["uniqueId"]
        )
        self.assertGreater(len(items), 500)

    def test_markdown_chunks_match_source_page(self):
        from rag.pipeline import index_nodes

        markdown = (ROOT / "data/document.md").read_text()
        parsed = json.loads((ROOT / "data/document.json").read_bytes())
        expected = next(
            block["pageNum"] + 1
            for block in parsed["Data"]["layouts"]
            if "1.0.1" in (block.get("markdownContent") or "")
        )
        meta = configuration("markdown", 512, 64) | {
            "index_version": "pages",
            "embedding_profile_id": "ollama:bge-m3",
            "original_filename": "document.md",
        }
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "document.md"
            source.write_text(markdown)
            nodes = index_nodes(source, Path(tmp), meta)
        self.assertGreater(len(nodes), 10)
        pages = []
        for node in nodes:
            page = node.metadata.get("page_pdf")
            self.assertIsInstance(page, int)
            content = node.get_content()
            self.assertIn(content, markdown)
            pages.append(page)
            if "1.0.1" in content:
                self.assertEqual(page, expected)
        self.assertGreater(len(set(pages)), 1)
        self.assertEqual(pages, sorted(pages))

    def test_registry_reopens_after_directory_removed(self):
        import shutil

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            db = Registry(root)
            db.reserve("sha", "v1", {"edition": "x"})
            shutil.rmtree(root)
            self.assertEqual(db.jobs(), [])
            db.reserve("sha", "v1", {"edition": "x"})
            self.assertEqual(len(db.jobs()), 1)

    def test_ing03_config(self):
        with self.assertRaises(ValueError):
            configuration("structure", 256, 128)
        self.assertEqual(configuration("semantic", 512, 64)["chunk_strategy"], "semantic")

    def test_each_text_strategy_emits_nodes(self):
        from unittest.mock import patch

        from llama_index.core.embeddings import MockEmbedding

        from rag.pipeline import index_nodes
        from rag.source import STRATEGIES

        text = "\n\n".join(
            f"# 第{i}章\n\n这是第{i}句说明。下一句继续说明检测要求。最后一句给出结论。"
            for i in range(1, 6)
        )
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.md"
            source.write_text(text)
            for strategy, _label in STRATEGIES:
                meta = configuration(strategy, 256, 32) | {
                    "index_version": strategy,
                    "embedding_profile_id": "ollama:bge-m3",
                }
                with patch(
                    "rag.pipeline.model", return_value=MockEmbedding(embed_dim=8)
                ):
                    nodes = index_nodes(source, Path(tmp), meta)
                self.assertGreater(len(nodes), 0, strategy)
                self.assertTrue(nodes[0].get_content().strip(), strategy)
                self.assertNotIn("page_pdf", nodes[0].metadata)
                if strategy == "markdown":
                    paths = {node.metadata.get("section_path") for node in nodes}
                    self.assertIn("第1章", paths)
                    self.assertIn("第5章", paths)

    def test_ing06_07_09(self):
        with TemporaryDirectory() as tmp:
            db = Registry(Path(tmp))
            job, created = db.reserve("abc", "v1", {"edition": "test"})
            self.assertTrue(created)
            self.assertFalse(db.reserve("abc", "v1", {})[1])
            db.finish(job, 3)
            self.assertEqual(db.active(), [])
            db.approve(job, "reviewer")
            self.assertEqual(Registry(Path(tmp)).active()[0]["id"], job)
            other, _ = db.reserve("abc", "v2", {})
            db.fail(other, "embedding")
            self.assertEqual(db.active()[0]["id"], job)
            db.delete("abc")
            self.assertEqual(db.active(), [])

    def test_ing07_key_conflicts(self):
        with TemporaryDirectory() as tmp:
            db = Registry(Path(tmp))
            first = db.reserve("a", "v", {}, "token")[0]
            self.assertEqual(first, db.reserve("a", "v", {}, "token")[0])
            with self.assertRaises(ValueError):
                db.reserve("b", "v", {}, "token")
            self.assertEqual(len(db.jobs()), 1)
