"""Unit tests for pipeline/analytics.py and pipeline/audit.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import analytics
import audit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestAnalyticsAndAudit(unittest.TestCase):
    def test_extract_dialogue_ratio(self):
        text = "他向前走去。「你好，世界。」他轻声说道。"
        ratio, diag_w, total_w = analytics._extract_dialogue_ratio(text)
        self.assertGreater(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)
        self.assertEqual(diag_w, 8)  # 「你好，世界。」包含全角标点共8字

    def test_bar_chart(self):
        bars = analytics._generate_bar_chart([1000, 2000], max_width=10)
        self.assertEqual(len(bars), 2)
        self.assertIn("1000", bars[0])
        self.assertIn("2000", bars[1])

    def test_extract_rules(self):
        world_text = """
## 七、硬性设定
- W1：光速不可逾越，量子纠缠无法传递超光速信息。
- W2：脑机接口必须植入在左侧颞叶。
"""
        rules = audit.extract_world_rules(world_text)
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0][0], "W1")
        self.assertEqual(rules[1][0], "W2")

    def test_extract_character_rules(self):
        char_text = """
## 角色一致性要点
- C1：林晏绝不在无防护状态下触碰未经哈希认证的数据终端。
- C2：沈莉始终以条例编号开篇进行沟通。
"""
        c_rules = audit.extract_character_rules(char_text)
        self.assertEqual(len(c_rules), 2)
        self.assertEqual(c_rules[0][0], "C1")
        self.assertEqual(c_rules[1][0], "C2")

    def test_extract_clues(self):
        outline_text = """
## 第1章 潜入
- 伏笔：终端屏幕闪过母亲林梅的签名代码。

## 第2章 危机
- 伏笔/回收：解析签名代码，确认这是四年前留下的预警。
"""
        clues = audit.extract_foreshadowing_clues(outline_text)
        self.assertEqual(len(clues), 2)
        self.assertFalse(clues[0]["is_recovery"])
        self.assertTrue(clues[1]["is_recovery"])


if __name__ == "__main__":
    unittest.main()
