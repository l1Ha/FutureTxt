"""CLI 解析回归测试。

历史教训：rebase 融合后 `run` 子命令曾丢失 `--force/--dry-run`，
而 `cmd_run/_ensure_api` 仍在访问它们，导致流水线一启动就 AttributeError。
本套件锁定"每个命令用到的参数都必须被解析器定义"。
"""

import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "pipeline"))
import run as run_cli  # noqa: E402


class TestCliParser(unittest.TestCase):
    def setUp(self):
        self.parser = run_cli.build_parser()

    def test_run_accepts_force_and_dry_run(self):
        args = self.parser.parse_args(
            ["run", "x", "--force", "--dry-run", "--only", "1-3"])
        self.assertTrue(args.force)
        self.assertTrue(args.dry_run)
        self.assertEqual(args.only, "1-3")
        self.assertEqual(args.stages, "all")

    def test_translate_subcommand_flags(self):
        args = self.parser.parse_args(["translate", "x", "--force", "--only", "2"])
        self.assertEqual(args.name, "x")
        self.assertTrue(args.force)
        self.assertEqual(args.only, "2")
        self.assertTrue(hasattr(args, "dry_run"))  # _ensure_api 需要

    def test_export_lang_choice(self):
        self.assertEqual(self.parser.parse_args(["export", "x"]).lang, "zh")
        self.assertEqual(
            self.parser.parse_args(["export", "x", "--lang", "en"]).lang, "en")

    def test_every_command_binds_func(self):
        cases = {
            "doctor": ["doctor"],
            "kb": ["kb"],
            "init": ["init", "x"],
            "run": ["run", "x"],
            "status": ["status", "x"],
            "stats": ["stats", "x"],
            "audit": ["audit", "x"],
            "export": ["export", "x"],
            "translate": ["translate", "x"],
        }
        for name, argv in cases.items():
            args = self.parser.parse_args(argv)
            self.assertTrue(callable(getattr(args, "func", None)), name)

    def test_cmd_run_attribute_contract(self):
        """cmd_run 访问的每个属性都必须存在于 run 子命令的 Namespace。"""
        args = self.parser.parse_args(["run", "x"])
        for attr in ("name", "stages", "only", "force", "dry_run"):
            self.assertTrue(hasattr(args, attr), attr)


if __name__ == "__main__":
    unittest.main()
