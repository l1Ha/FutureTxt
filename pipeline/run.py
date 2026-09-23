#!/usr/bin/env python
"""科幻小说自动化创作流水线 —— 命令行入口（纯标准库，Python 3.8+）。

用法示例：
  python pipeline/run.py config --api-key sk-xxx --base-url https://api.openai.com/v1 --model gpt-4o-mini
  python pipeline/run.py init 赛博侦探 --keywords 赛博朋克,侦探,记忆交易 --chapters 20 --words 3000
  python pipeline/run.py run 赛博侦探                      # 全流程
  python pipeline/run.py run 赛博侦探 --stages draft --only 1-10
  python pipeline/run.py status 赛博侦探
  python pipeline/run.py kb 黑暗森林
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kb  # noqa: E402
import llm  # noqa: E402
import stages  # noqa: E402
from stages import Project  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- 命令实现

def cmd_config(args):
    updates = {}
    for key in ("api_key", "base_url", "model", "temperature", "max_tokens"):
        val = getattr(args, key, None)
        if val is not None:
            updates[key] = val
    if not updates:
        try:
            cfg = llm.load_config(ROOT)
        except SystemExit:
            cfg = dict(llm.DEFAULTS)
            cfg["api_key"] = "(未设置)"
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return
    llm.save_config(ROOT, updates)
    print("✓ 配置已保存到 %s" % llm.config_path(ROOT))


def cmd_init(args):
    proj = Project(ROOT, args.name)
    if proj.exists() and not args.overwrite:
        raise SystemExit("项目已存在：%s（如需重置请加 --overwrite）" % proj.cfg_path)
    cfg = {
        "title": args.title or args.name,
        "keywords": [k.strip() for k in (args.keywords or "").split(",") if k.strip()],
        "premise": args.premise or "",
        "target_chapters": args.chapters,
        "words_per_chapter": args.words,
        "pov": args.pov,
        "tone": args.tone,
        "audience": args.audience,
        "extra": args.extra or "",
    }
    proj.save_config(cfg)
    proj.save_state({"stages": {}, "summaries": {}})
    os.makedirs(proj.chapters_dir(), exist_ok=True)
    os.makedirs(proj.reviews_dir(), exist_ok=True)
    print("✓ 项目已创建：%s" % proj.cfg_path)
    print("  下一步：python pipeline/run.py run %s" % args.name)


def _ensure_api(args):
    api = llm.load_config(ROOT)
    if args.dry_run:
        print("[dry-run] 使用模型：%s @ %s" % (api["model"], api["base_url"]))
    return api


def cmd_run(args):
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit("项目不存在，先执行：python pipeline/run.py init %s" % args.name)
    cfg = proj.config()
    todo = stages.STAGES if args.stages in ("all", None) else [
        s.strip() for s in args.stages.split(",") if s.strip()]
    bad = [s for s in todo if s not in stages.STAGES]
    if bad:
        raise SystemExit("未知阶段：%s\n可用：%s" % (",".join(bad), ",".join(stages.STAGES)))

    api = None
    if any(s != "assemble" for s in todo):
        api = _ensure_api(args)

    print("▶ 项目《%s》 阶段：%s" % (cfg.get("title"), " → ".join(todo)))
    for stage in todo:
        label = stages.STAGE_LABEL[stage]
        if stage in ("concept", "world", "characters", "outline"):
            fpath = getattr(proj, "f_" + stage)()
            if os.path.exists(fpath) and not args.force:
                print("• [%s] 已存在，跳过（--force 可重做）" % label)
                proj.mark(stage, "done")
                continue
        print("• [%s] 生成中…" % label)
        proj.mark(stage, "running")
        try:
            if stage == "concept":
                msg = stages.stage_concept(proj, cfg, api)
            elif stage == "world":
                msg = stages.stage_world(proj, cfg, api)
            elif stage == "characters":
                msg = stages.stage_characters(proj, cfg, api)
            elif stage == "outline":
                msg = stages.stage_outline(proj, cfg, api)
            elif stage == "draft":
                msg = stages.stage_draft(proj, cfg, api, only=args.only, force=args.force)
            elif stage == "review":
                msg = stages.stage_review(proj, cfg, api, only=args.only, force=args.force)
            elif stage == "revise":
                msg = stages.stage_revise(proj, cfg, api, only=args.only, force=args.force)
            else:
                msg = stages.stage_assemble(proj, cfg, api)
        except Exception as e:  # noqa: BLE001
            proj.mark(stage, "failed")
            print("✗ [%s] 失败：%s" % (label, e))
            raise SystemExit(1)
        proj.mark(stage, "done")
        print("  %s" % msg)
    print("✔ 完成")


def cmd_status(args):
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit("项目不存在：%s" % args.name)
    cfg = proj.config()
    st = proj.state()
    print("《%s》  %d章 × %d字（目标约 %d 字）"
          % (cfg.get("title"), cfg.get("target_chapters"), cfg.get("words_per_chapter"),
             cfg.get("target_chapters", 0) * cfg.get("words_per_chapter", 0)))
    print("关键词：%s" % ("、".join(cfg.get("keywords") or []) or "—"))
    print("阶段状态：")
    for s in stages.STAGES:
        mark = st.get("stages", {}).get(s, "未开始")
        icon = {"done": "✓", "failed": "✗", "running": "…"}.get(mark, " ")
        print("  %s %-10s %s" % (icon, stages.STAGE_LABEL[s], mark))
    files = proj.list_chapters()
    if files:
        total = sum(stages.word_count(stages.read(p)) for p in files)
        print("正文：%d 章，累计 %d 字" % (len(files), total))
    else:
        print("正文：尚未生成")


def cmd_kb(args):
    if not args.keyword:
        for path in kb.list_files(ROOT):
            print(os.path.relpath(path, ROOT))
        return
    hits = kb.search(ROOT, args.keyword, limit=args.limit)
    if not hits:
        print("未找到：%s" % args.keyword)
        return
    for rel, no, line in hits:
        print("%s:%d: %s" % (rel, no, line[:160]))


# ---------------------------------------------------------------- 参数解析

def build_parser():
    p = argparse.ArgumentParser(description="科幻小说自动化创作流水线")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("config", help="配置 LLM API（写入根目录 config.json）")
    c.add_argument("--api-key")
    c.add_argument("--base-url")
    c.add_argument("--model")
    c.add_argument("--temperature", type=float)
    c.add_argument("--max-tokens", type=int, dest="max_tokens")
    c.set_defaults(func=cmd_config)

    i = sub.add_parser("init", help="创建小说项目")
    i.add_argument("name", help="项目名（同时是目录名）")
    i.add_argument("--title", help="书名，默认同项目名")
    i.add_argument("--keywords", help="题材关键词，逗号分隔")
    i.add_argument("--premise", help="一句话故事前提")
    i.add_argument("--chapters", type=int, default=20, help="章节数，默认 20")
    i.add_argument("--words", type=int, default=3000, help="每章字数，默认 3000")
    i.add_argument("--pov", default="第三人称有限", help="叙事视角")
    i.add_argument("--tone", default="克制、具象、冷峻中有温度", help="文风基调")
    i.add_argument("--audience", default="成人科幻读者", help="目标读者")
    i.add_argument("--extra", help="其他要求")
    i.add_argument("--overwrite", action="store_true")
    i.set_defaults(func=cmd_init)

    r = sub.add_parser("run", help="执行流水线")
    r.add_argument("name")
    r.add_argument("--stages", default="all",
                   help="阶段子集，逗号分隔：concept,world,characters,outline,draft,review,revise,assemble")
    r.add_argument("--only", help="仅处理章节范围，如 3、1-5、1,4,7-9（作用于 draft/review/revise）")
    r.add_argument("--force", action="store_true", help="重做已有产物")
    r.add_argument("--dry-run", action="store_true", help="仅校验配置")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("status", help="查看项目状态")
    s.add_argument("name")
    s.set_defaults(func=cmd_status)

    k = sub.add_parser("kb", help="检索知识库（无关键词则列出全部文件）")
    k.add_argument("keyword", nargs="?")
    k.add_argument("--limit", type=int, default=30)
    k.set_defaults(func=cmd_kb)
    return p


def main(argv=None):
    # Windows 控制台默认 GBK，强制 UTF-8 输出避免乱码与编码异常
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
