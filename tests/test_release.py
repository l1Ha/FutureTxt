"""Unit tests for pipeline/release.py（发行打包：前缀校验、版本递增、附件命名、说明生成）。"""

import json
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "pipeline"))
import release  # noqa: E402
from stages import Project  # noqa: E402


class TestReleasePure(unittest.TestCase):
    def test_validate_prefix(self):
        self.assertEqual(release.validate_prefix(" JuanYangJiYuan "), "JuanYangJiYuan")
        self.assertEqual(release.validate_prefix("abc-1.2_x"), "abc-1.2_x")
        for bad in ("", "   ", "圈养纪元", "a b", "书.epub"):
            with self.assertRaises(ValueError):
                release.validate_prefix(bad)

    def test_bump_tag(self):
        self.assertEqual(release.bump_tag([]), "novels-v1.0")
        self.assertEqual(release.bump_tag(["novels-v1.0"]), "novels-v1.1")
        self.assertEqual(release.bump_tag(["novels-v1.0", "novels-v1.1"]), "novels-v1.2")
        self.assertEqual(release.bump_tag(["novels-v1.3", "novels-v2.0"]), "novels-v2.1")
        # 无关标签被忽略
        self.assertEqual(release.bump_tag(["v1.0", "release-7", "novels-v1.4"]), "novels-v1.5")

    def test_asset_names_ascii_only(self):
        names = release.asset_names("QuanJuan", has_en=False)
        self.assertEqual([n for _, n in names],
                         ["QuanJuan.epub", "QuanJuan.html", "QuanJuan.txt", "QuanJuan.pdf"])
        both = release.asset_names("QuanJuan", has_en=True)
        self.assertEqual(len(both), 8)
        self.assertIn(("en", "QuanJuan-EN.epub"), both)
        for _, n in both:
            self.assertTrue(release.ASCII_RE.match(n), n)


class TestReleasePackage(unittest.TestCase):
    """用临时项目验证：附件按 ASCII 命名打包 + 双语说明生成 + dry-run 编排。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.proj_dir = os.path.join(root, "projects", "圈养纪元")
        os.makedirs(os.path.join(self.proj_dir, "chapters"))
        os.makedirs(os.path.join(self.proj_dir, "dist"))
        os.makedirs(os.path.join(self.proj_dir, "dist_en"))
        with open(os.path.join(self.proj_dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "圈养纪元", "keywords": ["奴隶制", "反乌托邦"],
                       "asset_prefix": "JuanYangJiYuan"}, f, ensure_ascii=False)
        with open(os.path.join(self.proj_dir, "chapters", "chapter_001.md"), "w",
                  encoding="utf-8") as f:
            f.write("# 第1章 债务枷锁\n\n" + "他欠下的债永远还不清。" * 20)
        for ext in ("epub", "html", "txt", "pdf"):
            with open(os.path.join(self.proj_dir, "dist", "圈养纪元." + ext), "w",
                      encoding="utf-8") as f:
                f.write("zh-" + ext)
            with open(os.path.join(self.proj_dir, "dist_en",
                                   "圈养纪元 (English Edition)." + ext), "w",
                      encoding="utf-8") as f:
                f.write("en-" + ext)
        # 中文简介写在最后（上面的循环会覆盖同名 txt）
        with open(os.path.join(self.proj_dir, "dist", "圈养纪元.txt"), "w",
                  encoding="utf-8") as f:
            f.write("《圈养纪元》\n====\n【作品简介】\n债务按秒复利，实验体被编号圈养。\n====\n")
        with open(os.path.join(self.proj_dir, "blurb_en.md"), "w", encoding="utf-8") as f:
            f.write("A dystopian novella about automated production and debt slavery.\n")
        self.proj = Project(root, "圈养纪元")

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_assets_names_and_content(self):
        out = os.path.join(self.proj_dir, "release_build")
        assets = release.collect_assets(self.proj, out, "JuanYangJiYuan")
        names = sorted(os.path.basename(d) for _, _, d in assets)
        self.assertEqual(names, [
            "JuanYangJiYuan-EN.epub", "JuanYangJiYuan-EN.html", "JuanYangJiYuan-EN.pdf",
            "JuanYangJiYuan-EN.txt", "JuanYangJiYuan.epub", "JuanYangJiYuan.html",
            "JuanYangJiYuan.pdf", "JuanYangJiYuan.txt"])
        for kind, src, dst in assets:
            with open(dst, encoding="utf-8") as f:
                body = f.read()
            if kind == "en":
                self.assertTrue(body.startswith("en-"), dst)
            else:
                # 中文 txt 在夹具里被换成含简介的版本
                self.assertTrue(body.startswith("zh-") or "【作品简介】" in body, dst)

    def test_compose_notes_bilingual(self):
        notes = release.compose_notes(self.proj, "JuanYangJiYuan", "novels-v1.1")
        self.assertIn("债务按秒复利", notes)                       # 中文简介
        self.assertIn("dystopian novella", notes)                  # 英文简介
        self.assertIn("`JuanYangJiYuan-EN.epub`", notes)           # 对照表
        self.assertIn("novels-v1.1", notes)

    def test_resolve_prefix_from_project_json(self):
        self.assertEqual(release.resolve_prefix(self.proj), "JuanYangJiYuan")
        self.assertEqual(release.resolve_prefix(self.proj, "OtherPrefix"), "OtherPrefix")

    def test_run_release_dry_run(self):
        report = release.run_release(self.proj, tag="novels-v9.9", dry_run=True)
        self.assertIn("dry-run", report)
        self.assertIn("novels-v9.9", report)
        self.assertIn("JuanYangJiYuan-EN.txt", report)
        self.assertTrue(os.path.exists(
            os.path.join(self.proj_dir, "release_build", "release_notes.md")))


if __name__ == "__main__":
    unittest.main()
