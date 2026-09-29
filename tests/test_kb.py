"""Unit tests for pipeline/kb.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import kb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestKB(unittest.TestCase):
    def test_list_files(self):
        files = kb.list_files(ROOT)
        self.assertGreaterEqual(len(files), 30)
        self.assertTrue(all(f.endswith(".md") for f in files))

    def test_clip_preserve_edges(self):
        text = "HEAD_" + ("X" * 1000) + "_TAIL"
        clipped = kb._clip_preserve_edges(text, 100)
        self.assertLessEqual(len(clipped), 150)
        self.assertTrue(clipped.startswith("HEAD_"))
        self.assertTrue(clipped.endswith("_TAIL"))

    def test_search_and_ranking(self):
        hits = kb.search(ROOT, "戴森球", limit=5)
        self.assertGreater(len(hits), 0)
        rel, line_no, content = hits[0]
        self.assertTrue("戴森" in content or "dyson" in content.lower())
        self.assertIsInstance(line_no, int)

    def test_load_budget_distribution(self):
        # 验证 world 阶段加载不会饿死 03-科学顾问
        text = kb.load(ROOT, ["02-世界观", "03-科学顾问"], cap=6000)
        self.assertIn("世界观", text)
        self.assertIn("科学顾问", text)

    def test_retrieve_snippets(self):
        snippets = kb.retrieve_snippets(ROOT, "黑洞 视界 引力", cap=2000, max_snippets=2)
        self.assertGreater(len(snippets), 0)
        self.assertIn("参考模块", snippets)


if __name__ == "__main__":
    unittest.main()
