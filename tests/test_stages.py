"""Unit tests for pipeline/stages.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import stages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestStages(unittest.TestCase):
    def test_outline_count_block_fixed(self):
        auto, rule, act, last = stages.outline_count_block(
            {"target_chapters": 6, "words_per_chapter": 2500})
        self.assertFalse(auto)
        self.assertIn("严格输出 6 章（不得多、不得少）", rule)
        self.assertIn("直到第6章", last)
        self.assertIn("三幕式", act)

    def test_outline_count_block_auto(self):
        auto, rule, act, last = stages.outline_count_block(
            {"target_chapters": 8, "words_per_chapter": 2500, "chapters_mode": "auto",
             "min_chapters": 5, "max_chapters": 12})
        self.assertTrue(auto)
        self.assertIn("章数由情节决定", rule)
        self.assertIn("建议 5~12 章", rule)
        self.assertNotIn("严格输出", rule)
        self.assertIn("直到最后一章", last)
        self.assertIn("按实际章数自行换算比例", act)

    def test_quality_rules_includes_reality_mapping(self):
        # 「未来为镜：设定映射当下」必须作为红线注入写作/修订提示词
        rules = stages.quality_rules(2500)
        self.assertIn("映射当下", rules)
        self.assertIn("现实", rules)
        self.assertIn("2500", rules)  # 仍带字数参数

    def test_mapping_rules_injected_into_setting_stages(self):
        # 概念与世界观阶段必须能拿到质量规则（含映射原则），否则开书时不会产出映射表
        import kb
        for stage_name in ("concept", "world", "draft", "review", "revise", "continuity"):
            mods = kb.STAGE_MODULES[stage_name]
            self.assertTrue(any(m.startswith("09") for m in mods), stage_name)

    def test_word_count(self):
        text = "未来 科技 探索\nHello World!"
        # 中文6字 + 英文与标点11字 = 17
        self.assertEqual(stages.word_count(text), 17)

    def test_chapter_no(self):
        self.assertEqual(stages.chapter_no("chapter_007.md"), 7)
        self.assertEqual(stages.chapter_no("/path/to/chapter_012_审校.md"), 12)

    def test_clip(self):
        t = "A" * 500
        clipped = stages.clip(t, 100)
        self.assertIn("…（中间略）…", clipped)
        self.assertLessEqual(len(clipped), 120)

    def test_parse_outline(self):
        sample = """# 全书大纲
## 故事线概览
简介正文

## 第1章 记忆之渊
- 场景：霓虹地下城
- 核心冲突：记忆被盗

## 第2章 暗网追凶
- 场景：浮空艇
- 核心冲突：遭遇伏击
"""
        parsed = stages.parse_outline(sample)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0][0], 1)
        self.assertEqual(parsed[0][1], "记忆之渊")
        self.assertEqual(parsed[1][0], 2)
        self.assertEqual(parsed[1][1], "暗网追凶")

    def test_project_state_and_usage(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = stages.Project(tmpdir, "mock_novel")
            proj.save_config({"title": "Mock Novel"})
            proj.save_state({"stages": {}})
            proj.track_usage("test_stage", {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
            st = proj.state()
            self.assertIn("token_usage", st)
            self.assertEqual(st["token_usage"]["total_tokens"], 150)


if __name__ == "__main__":
    unittest.main()
