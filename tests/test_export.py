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


    def test_strip_anchors(self):
        src = (
            "误报率不得超过 0.8%（W6），根据 W4，档案馆年均输出 1.2 kW。\n\n"
            "他盯着 C1 的光点；按 W2 规定，24 小时内必须服药，well within W3。\n"
            "参照 W3C 标准，试剂 C12 与数据 W2 传输保持原样。\n"
        )
        out = export.strip_anchors(src, valid_ids={"W2", "W3", "W4", "W6", "C1"})
        self.assertNotIn("（W6）", out)
        self.assertNotIn("根据 W4", out)
        self.assertNotIn("C1 的", out)
        self.assertNotIn("按 W2 规定", out)
        self.assertNotIn("within W3", out)
        self.assertIn("0.8%", out)
        self.assertIn("档案馆", out)
        self.assertIn("W3C", out)  # 非锚点编号不误杀
        self.assertIn("C12", out)
        self.assertIn("数据传输", out)

    def test_strip_anchors_without_ids_keeps_bare(self):
        # 未提供已定义编号时，裸编号保守保留（仅括号/引导/挂接式被剥离）
        out = export.strip_anchors("根据 W4，他知道（W5）成立，C1 的光点闪烁。")
        self.assertNotIn("（W5）", out)
        self.assertNotIn("根据 W4", out)
        self.assertNotIn("C1 的", out)

    def test_strip_anchors_protects_code_spans(self):
        # 反引号代码段（哈希/编号）整体保护，即使内容形如合法编号
        out = export.strip_anchors(
            "飞行记忆哈希为 `3F9A…C2`，与 `Z` 一致（W6）。",
            valid_ids={"C2", "W6"},
        )
        self.assertIn("`3F9A…C2`", out)   # 哈希原样保留
        self.assertNotIn("（W6）", out)    # 锚点照常剥离

    def test_strip_anchors_daily_details(self):
        src = (
            "每餐约 0.03 信用点（日常细节2），“根据MemBazaar日常细节13，违规罚500 CP。”\n"
            "这正是日常细节1所描述的调光机制；标志（见文化日常细节第11条）。\n"
            "LED 模拟日出。（起床与光照）她继续做饭。\n"
            "她的话语间插入了一段日常细节——看似琐碎，却是生活的质地。\n"
        )
        out = export.strip_anchors(src, valid_ids=set(), daily_titles=["起床与光照"])
        self.assertNotIn("（日常细节2）", out)
        self.assertNotIn("日常细节13", out)
        self.assertNotIn("日常细节1所描述的", out)
        self.assertNotIn("见文化日常细节第11条", out)
        self.assertNotIn("（起床与光照）", out)
        self.assertIn("一段日常细节——", out)  # 非引用的正常行文保留

    def test_strip_anchors_fixup_sentences(self):
        out = export.strip_anchors(
            "为了满足 C7 而设计；甚至触发 W8——须参保；符合 W3 规定。"
            "这是 W15 中提到的急救箱；误差 1.3 厘米，well within W3；受W10保护。"
            "这直接触犯了 W13——须知情同意。",
            valid_ids={"C7", "W8", "W3", "W15", "W10", "W13"},
        )
        self.assertIn("为了满足要求而设计", out)
        self.assertIn("触发相关规定——", out)
        self.assertIn("符合规定。", out)
        self.assertNotIn("中提到", out)
        self.assertNotIn("well within", out)
        self.assertIn("受规则保护", out)
        self.assertIn("触犯了规定——", out)


if __name__ == "__main__":
    unittest.main()
