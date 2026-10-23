"""Unit tests for pipeline/translate.py（纯函数）与双语导出链路（export lang='en'）。"""

import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "pipeline"))
import export  # noqa: E402
import translate  # noqa: E402


class TestTranslateHelpers(unittest.TestCase):
    def test_chapter_heading(self):
        self.assertEqual(translate.chapter_heading("# 第3章 债务枷锁\n\n正文"),
                         (3, "债务枷锁"))
        self.assertEqual(translate.chapter_heading("### 第 12 章 铁笼\n正文"),
                         (12, "铁笼"))
        self.assertEqual(translate.chapter_heading("正文没有标题"), (0, ""))

    def test_normalize_heading_from_plain_text(self):
        out = translate.normalize_heading("The ledger was empty.\n", 2, "The Ledger")
        self.assertTrue(out.startswith("# Chapter 2: The Ledger\n"))
        self.assertIn("The ledger was empty.", out)

    def test_normalize_heading_strips_model_prefix(self):
        out = translate.normalize_heading("# Chapter 7: Debt\n\nBody.", 7, "")
        self.assertTrue(out.startswith("# Chapter 7: Debt\n"))
        self.assertNotIn("Chapter 7: Chapter", out)  # 不产生双层前缀

    def test_normalize_heading_fixes_wrong_number(self):
        out = translate.normalize_heading("## Chapter 2: Debt\n\nBody.", 5, "Debt")
        self.assertTrue(out.startswith("# Chapter 5: Debt\n"))

    def test_mask_and_unmask_code_spans(self):
        src = "哈希 `3F9A…C2E7` 与 `Z` 保持"
        masked, spans = translate.mask_code(src)
        self.assertNotIn("3F9A", masked)
        self.assertEqual(translate.unmask_code(masked, spans), src)


class TestBilingualExport(unittest.TestCase):
    """英文版导出：读 chapters_en/、落 dist_en/、英文标签、锚点照常剥离。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        os.makedirs(os.path.join(root, "chapters"))
        os.makedirs(os.path.join(root, "chapters_en"))
        with open(os.path.join(root, "01-世界观.md"), "w", encoding="utf-8") as f:
            f.write("# 世界观\n\n| **W1** | 债务不可清偿。 |\n")
        with open(os.path.join(root, "02-角色.md"), "w", encoding="utf-8") as f:
            f.write("# 角色\n\n- **C1**：主角编号 T-9。\n")
        with open(os.path.join(root, "chapters", "chapter_001.md"), "w", encoding="utf-8") as f:
            f.write("# 第1章 债务枷锁\n\n他欠下的债（W1）永远还不清。\n")
        with open(os.path.join(root, "chapters_en", "chapter_001.md"), "w", encoding="utf-8") as f:
            f.write("# Chapter 1: The Debt Chain\n\nThe debt (W1) can never be repaid.\n")
        with open(os.path.join(root, "blurb_en.md"), "w", encoding="utf-8") as f:
            f.write("A dystopian novella about automated production and debt slavery.\n")

        class _Proj:
            name = "testproj"

            def __init__(self, root):
                self.root = root

            def config(self):
                return {"title": "圈养纪元", "author": "FutureTxt AI Writer", "premise": "债务社会"}

            def f_concept(self):
                return os.path.join(self.root, "00-创作概念.md")

            def f_world(self):
                return os.path.join(self.root, "01-世界观.md")

            def f_characters(self):
                return os.path.join(self.root, "02-角色.md")

            def list_chapters(self):
                return [os.path.join(self.root, "chapters", "chapter_001.md")]

            def path(self, *p):
                return os.path.join(self.root, *p)

        self.proj = _Proj(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_en_uses_chapters_en_and_dist_en(self):
        res = export.export_all(self.proj, formats=["txt"], lang="en")
        self.assertTrue(res["txt"].endswith(
            os.path.join("dist_en", "圈养纪元 (English Edition).txt")))
        with open(res["txt"], encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("A dystopian novella", txt)        # 英文简介来自 blurb_en.md
        self.assertIn("By FutureTxt AI Writer", txt)      # 英文标签
        self.assertIn("[ SYNOPSIS ]", txt)
        self.assertIn("Chapter 1: The Debt Chain", txt)   # 英文章节正文
        self.assertNotIn("W1", txt)                       # 锚点照常剥离
        self.assertNotIn("（W1）", txt)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "dist")))  # 不碰中文 dist

    def test_export_zh_unchanged(self):
        res = export.export_all(self.proj, formats=["txt"], lang="zh")
        self.assertTrue(res["txt"].endswith(os.path.join("dist", "圈养纪元.txt")))
        with open(res["txt"], encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("《圈养纪元》", txt)
        self.assertIn("作者：FutureTxt AI Writer", txt)
        self.assertNotIn("W1", txt)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp.name, "dist")))

    def test_export_en_without_translation_raises(self):
        os.remove(os.path.join(self.tmp.name, "chapters_en", "chapter_001.md"))
        with self.assertRaises(RuntimeError):
            export.export_all(self.proj, formats=["txt"], lang="en")


if __name__ == "__main__":
    unittest.main()
