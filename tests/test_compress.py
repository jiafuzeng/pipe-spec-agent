import unittest

from app.agent.utils.compress import compress_item, compress_items, render_clauses
from app.knowledge.retrieval import citation_spans

CHAPTER = """# 3 基本规定

3.0.1 从事城镇排水管道检测和评估的单位应具备相应的资质。

3.0.4 以结构性状况为目的的普查周期宜为 5a～10a，以功能性状况为目的的普查周期宜为 1a～2a。当遇到下列情况之一时，普查周期可相应缩短：

1 流砂易发、湿陷性土等特殊地区的管道；

2 管龄 30a 以上的管道。
"""


class CompressTests(unittest.TestCase):
    def _item(self):
        return {
            "clause_no": "3.0.1",
            "quote": CHAPTER,
            "citation_spans": citation_spans(CHAPTER, "3.0.1", 11),
        }

    def test_query_keeps_matching_clause_not_whole_chapter(self):
        packed = compress_items([self._item()], "普查周期分别是多久")
        clauses = {row["clause_no"] for row in packed}
        self.assertEqual(clauses, {"3.0.4"})
        body = packed[0]["quote"]
        self.assertIn("5a～10a", body)
        self.assertIn("1a～2a", body)
        self.assertIn("管龄 30a", body)
        self.assertNotIn("资质", body)
        self.assertLess(len(body), len(CHAPTER))
        self.assertIn("3.0.4", render_clauses(packed))
        self.assertNotIn("资质", render_clauses(packed))

    def test_query_keeps_other_clause_in_same_chunk(self):
        packed = compress_items([self._item()], "检测单位应具备什么资质")
        self.assertEqual({row["clause_no"] for row in packed}, {"3.0.1"})
        self.assertIn("资质", packed[0]["quote"])
        self.assertNotIn("5a～10a", packed[0]["quote"])

    def test_plain_quote_is_compacted(self):
        rows = compress_item({"clause_no": "1.0.1", "quote": "1.0.1  \n制定本规程。"})
        self.assertEqual(rows[0]["clause_no"], "1.0.1")
        self.assertEqual(rows[0]["quote"], "1.0.1 制定本规程。")
