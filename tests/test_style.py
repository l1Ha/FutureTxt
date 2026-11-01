"""Unit tests for pipeline/style.py（确定性文风体检）。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import style
from stages import Project


class TestStyleDetectors(unittest.TestCase):
    def test_cliche_detection_and_overlap(self):
        text = "空气仿佛凝固。他没有说话。\n她笑了笑，泪水夺眶而出。"
        hits = style.find_cliches(text)
        phrases = [h["phrase"] for h in hits]
        self.assertIn("空气仿佛凝固", phrases)
        self.assertIn("泪水夺眶而出", phrases)
        # 长词优先，不与「空气凝固」重复计数
        self.assertNotIn("空气凝固", phrases)

    def test_ai_template_detection(self):
        text = "这不是逃跑，而是回家。\n他明白了，事情没有这么简单。"
        hits = style.find_ai_templates(text)
        labels = [h["label"] for h in hits]
        self.assertTrue(any("不是…而是" in x for x in labels), labels)
        self.assertTrue(any("他明白了" in x for x in labels), labels)

    def test_sentence_and_paragraph_stats(self):
        s = style.sentence_stats("# 第1章\n\n第一句。第二句？第三句！")
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["avg"], 3.0)
        p = style.paragraph_stats("# 第1章\n\n" + "很长的段落" * 80)
        self.assertEqual(p["count"], 1)
        self.assertEqual(p["over_300"], 1)

    def test_dialogue_ratio(self):
        text = "他说：「你好。」然后转身走了。"
        ratio = style.dialogue_ratio(text)
        self.assertGreater(ratio, 0.0)
        self.assertLess(ratio, 1.0)

    def test_repeated_sentences_and_openings(self):
        sent = "他沿着河岸一直走到天黑才停下来。"
        chapters = [(1, sent + "\n\n他沿着河岸一直走，风从背后吹来。"),
                    (2, sent + "\n\n他沿着河岸一直走，水面没有声音。"),
                    (3, "他沿着河岸一直走，天已经完全黑了。")]
        dups = style.find_dup_sentences(chapters)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["chapters"], [1, 2])
        openings = style.find_dup_openings(chapters)
        self.assertTrue(openings)
        self.assertGreaterEqual(openings[0]["count"], 3)

    def test_similar_chapters_detection(self):
        same = "他沿着河岸一直走，风从背后吹来，水面上浮着一层薄雾。" * 40
        other = "她坐在窗边，把一张旧车票翻来覆去地看，车票边角已经卷了。" * 40
        chapters = [(1, same), (2, same.replace("薄雾", "雾气")), (3, other)]
        pairs = style.find_similar_chapters(chapters)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]["a"], pairs[0]["b"]), (1, 2))
        self.assertGreaterEqual(pairs[0]["cover"], style.CHAPTER_SIM_MIN)

    def test_end_marker_detection(self):
        clean = style.find_end_markers("他把碗放回桌上，走了。")
        self.assertEqual(clean["count"], 0)
        single = style.find_end_markers("他走了。\n\n（全文完）")
        self.assertEqual(single["count"], 1)
        self.assertEqual(single["trail_chars"], 0)
        double = style.find_end_markers(
            "他走了。（全文完）\n\n" + "第二天，施工队又来了。" * 20 + "\n\n（全文完）")
        self.assertEqual(double["count"], 2)
        self.assertGreater(double["trail_chars"], style.TRAIL_AFTER_END)

    def test_top_ngrams(self):
        text = "照护关系很重要。" * 6
        grams = style.top_ngrams(text, min_count=5)
        self.assertTrue(any(g["phrase"] == "照护关系" for g in grams), grams)

    def test_report_and_digest(self):
        text = ("空气仿佛凝固。这不是逃跑，而是回家。他明白了，事情没有这么简单。\n\n"
                + "他说：「走吧。」" * 20)
        res = style.analyze_text(text)
        report = style.format_report({
            "title": "测试", "form": "short", "chapters": [dict(res, chapter=1, title="第1章")],
            "total_words": res["words"], "dialogue_ratio": res["dialogue_ratio"],
            "sentences": res["sentences"], "paragraphs": res["paragraphs"],
            "cliche_hits": [dict(h, chapter=1) for h in res["cliche_hits"]],
            "template_hits": [dict(h, chapter=1) for h in res["template_hits"]],
            "tic_words": res["tic_words"], "top_ngrams": res["top_ngrams"],
            "dup_sentences": [], "dup_openings": [], "score": 70, "grade": "C",
        })
        self.assertIn("文风体检", report)
        self.assertIn("陈词滥调", report)
        self.assertIn("体检分", report)


class TestStyleProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        pdir = os.path.join(root, "projects", "测试")
        os.makedirs(os.path.join(pdir, "chapters"))
        with open(os.path.join(pdir, "project.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "测试", "work_type": "short", "words_per_chapter": 1000},
                      f, ensure_ascii=False)
        with open(os.path.join(pdir, "chapters", "chapter_001.md"), "w", encoding="utf-8") as f:
            f.write("# 第1章\n\n空气仿佛凝固。他明白了，这不是结束，而是开始。\n")
        self.proj = Project(root, "测试")

    def tearDown(self):
        self.tmp.cleanup()

    def test_analyze_project_and_chapter_filter(self):
        res = style.analyze_project(self.proj)
        self.assertEqual(len(res["chapters"]), 1)
        self.assertEqual(res["form"], "short")
        self.assertGreater(res["total_words"], 0)
        self.assertTrue(res["cliche_hits"])
        none = style.analyze_project(self.proj, chapter=9)
        self.assertEqual(none["chapters"], [])


if __name__ == "__main__":
    unittest.main()
