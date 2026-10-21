"""Unit tests for pipeline/export.py."""

import os
import re
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
            "这直接触犯了 W13——须知情同意。“按 W9规定，超采将被扣除配额。”",
            valid_ids={"C7", "W8", "W3", "W15", "W10", "W13", "W9"},
        )
        self.assertIn("为了满足要求而设计", out)
        self.assertIn("触发相关规定——", out)
        self.assertIn("符合规定。", out)
        self.assertNotIn("中提到", out)
        self.assertNotIn("well within", out)
        self.assertIn("受规则保护", out)
        self.assertIn("触犯了规定——", out)
        self.assertIn("按规定，超采将被扣除配额", out)  # 介词悬空修复：按 W9规定 → 按规定
        self.assertNotIn("按超采", out)

    def test_export_all_e2e_three_anchor_families(self):
        # 端到端：迷你项目（火星采冰穹顶《冰下回声》）走真实 export_all，
        # 覆盖三族锚点、组合/半角括号、引号前置引导式、9 条病句 fixup、
        # 陷阱词/哈希/行文保护、三格式零残留。桩类接口与 stages.Project 对齐。
        class _MiniProject:
            name = "bingxia-test"

            def __init__(self, root):
                self.root = root

            def config(self):
                return {"title": "冰下回声（测试）",
                        "premise": "穹顶采冰人发现配给账目与哈希对不上。"}

            def f_concept(self):
                return os.path.join(self.root, "00-创作概念.md")

            def f_world(self):
                return os.path.join(self.root, "01-世界观.md")

            def f_characters(self):
                return os.path.join(self.root, "02-角色.md")

            def list_chapters(self):
                return [os.path.join(self.root, "chapters", "chapter_001.md")]

            def path(self, *parts):
                return os.path.join(self.root, *parts)

        world = (
            "# 世界观\n\n"
            "- **文化与日常**\n"
            "- **日常细节（每项至少出现一次正文）**：\n"
            "  1. **起床与光照**：穹顶居所按生物钟模拟日出。\n"
            "  3. **工位与照明**：全息屏按工位等级自动调光。\n"
            "  5. **配给与口粮**：配给口粮每餐约 0.4 升藻液。\n\n"
            "## 硬性设定（W1…）\n\n"
            "| 编号 | 硬性设定内容 |\n|------|--------------|\n"
            "| **W1** | 冗余校验链由三节点互检构成。 |\n"
            "| **W2** | 水循环泵每 7 次告警须人工复位。 |\n"
            "| **W3** | 采冰井校准误差不超过 3 厘米。 |\n"
            "| **W4** | 单次下探不得超过 8 小时。 |\n"
            "| **W6** | 密封圈每 90 天强制更换。 |\n"
            "| **W7** | 上传哈希采用量子抗签名。 |\n"
            "| **W8** | 私自改造舱体罚没全部配额。 |\n"
            "| **W9** | 超采按三倍配额扣除。 |\n"
        )
        chars = "# 角色\n\n- **一致性要点（C1…）**\n- **C1**：密封圈特写须体现老化裂纹。\n"
        chapter = (
            "# 第1章 冰下回声\n\n"
            "穹顶农场的水循环泵在凌晨三点发出第七次告警（W2）。根据 W4，冰层下 120 米的"
            "采冰井每次下探不得超过 8 小时，而他的潜水计已显示 45:12。\n\n"
            "他盯着控制屏上的哈希校验 `9F2E…C3A7`，确认上传未被篡改（W7）。这是 W1中提到的"
            "冗余校验链。冗余链与配额联动（W2、W4），双因子校验 (W7) 已启用。\n\n"
            "“按 W9规定，超采将被扣除配额，”队长说，“但热失效已触发。”\n\n"
            "舱内的全息屏按工位等级自动调光（日常细节3），这正是日常细节3所描述的光通量动态"
            "分配机制。备忘（日常细节：配给口粮含应急条款）。根据日常细节5，配给口粮每餐约 "
            "0.4 升藻液。“误差在 3 厘米内，well within W3。”\n\n"
            "他想起老家的一段日常细节——雨落在瓦上的声音。这与 W3C 标准、试剂 C12 无关。\n\n"
            "必须符合 W6 规定，且受W8保护。为了满足 C1 而设计的密封圈已经老化。\n\n"
            "（起床与光照）他按下复位钮。\n"
        )

        root = self.temp_dir.name
        os.makedirs(os.path.join(root, "chapters"))
        for rel, body in (("01-世界观.md", world), ("02-角色.md", chars),
                          (os.path.join("chapters", "chapter_001.md"), chapter)):
            with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
                f.write(body)

        proj = _MiniProject(root)
        # 文档解析：定义编号与日常细节条目标题
        self.assertEqual(export._defined_daily_titles(proj),
                         ["起床与光照", "工位与照明", "配给与口粮"])
        ids = export._defined_anchor_ids(proj)
        self.assertIn("W9", ids)
        self.assertIn("C1", ids)
        self.assertNotIn("C12", ids)  # 正文陷阱词不会被文档解析为编号

        res = export.export_all(proj, formats=["epub", "html", "txt"])
        with open(res["txt"], encoding="utf-8") as f:
            txt = f.read()
        with open(res["html"], encoding="utf-8") as f:
            htm = f.read()
        with zipfile.ZipFile(res["epub"]) as zf:
            epx = "".join(zf.read(n).decode("utf-8")
                          for n in zf.namelist() if n.endswith(".xhtml"))

        # 三族锚点全部剥离
        for anchor in ("（W2）", "（W2、W4）", "(W7)", "（W7）",
                       "根据 W4", "按 W9", "符合 W6", "为了满足 C1", "受W8保护",
                       "日常细节3", "日常细节5", "（日常细节：", "（起床与光照）",
                       "well within", "中提到", "所描述"):
            self.assertNotIn(anchor, txt, anchor)
        # fixup 后句子接顺
        self.assertIn("必须符合规定", txt)
        self.assertIn("为了满足要求而设计", txt)
        self.assertIn("受规则保护", txt)
        self.assertIn("这是冗余校验链", txt)
        self.assertIn("这正是光通量动态分配机制", txt)
        self.assertIn("误差在 3 厘米内", txt)
        self.assertIn("超采将被扣除配额", txt)
        self.assertIn("按规定，超采将被扣除配额", txt)  # 引号前置「按 W9规定，」→「按规定，」
        self.assertNotIn("按超采", txt)
        # 陷阱词、哈希、正常行文原样保留
        self.assertIn("`9F2E…C3A7`", txt)
        self.assertIn("W3C", txt)
        self.assertIn("C12", txt)
        self.assertIn("一段日常细节", txt)
        self.assertIn("热失效已触发", txt)
        # 三格式零锚点残留（C12/W3C 形如编号但为故意保留的陷阱词，扫描前遮蔽）
        pat = re.compile(r"(?<![A-Za-z0-9])[WC]\d+(?![A-Za-z0-9])")
        for src in (txt, htm, epx):
            self.assertIsNone(pat.search(src.replace("C12", "C-x").replace("W3C", "W-x")))
            self.assertIsNone(re.search(r"日常细节\d", src))


if __name__ == "__main__":
    unittest.main()
