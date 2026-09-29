"""Unit tests for pipeline/export.py."""

import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import export


class TestExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chapters = [
            ("第1章 觉醒", "# 第1章 觉醒\n\n他在冰冷的液氮舱中苏醒。\n\n「我是谁？」他低语。"),
            ("第2章 跃迁", "# 第2章 跃迁\n\n星舰引擎轰鸣，曲率泡迅速张开。"),
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_epub(self):
        out_path = os.path.join(self.temp_dir.name, "test_book.epub")
        export.export_epub(
            out_path,
            title="测试科幻小说",
            author="科幻作家",
            description="这是一个思想实验故事。",
            chapters=self.chapters,
        )
        self.assertTrue(os.path.exists(out_path))

        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            # 验证首个条目是未压缩的 mimetype
            self.assertEqual(names[0], "mimetype")
            self.assertEqual(zf.read("mimetype").decode("ascii"), "application/epub+zip")
            self.assertIn("META-INF/container.xml", names)
            self.assertIn("OEBPS/content.opf", names)
            self.assertIn("OEBPS/toc.ncx", names)
            self.assertIn("OEBPS/chapter_001.xhtml", names)

    def test_export_html(self):
        out_path = os.path.join(self.temp_dir.name, "test_book.html")
        export.export_html(
            out_path,
            title="测试科幻小说",
            author="科幻作家",
            description="简介内容",
            chapters=self.chapters,
        )
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("测试科幻小说", content)
        self.assertIn("第1章 觉醒", content)
        self.assertIn("goToChapter", content)

    def test_export_txt(self):
        out_path = os.path.join(self.temp_dir.name, "test_book.txt")
        export.export_txt(
            out_path,
            title="测试科幻小说",
            author="科幻作家",
            description="简介内容",
            chapters=self.chapters,
        )
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("《测试科幻小说》", content)
        self.assertIn("\u3000\u3000他在冰冷的液氮舱中苏醒。", content)


if __name__ == "__main__":
    unittest.main()
