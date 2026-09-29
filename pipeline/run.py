#!/usr/bin/env python
"""科幻小说自动化创作流水线 —— 命令行入口（纯标准库，Python 3.8+）。

主要命令：
  python pipeline/run.py doctor                             # 系统健康自检与 API 连通性测试
  python pipeline/run.py config --api-key sk-xxx            # 配置 LLM API
  python pipeline/run.py init 赛博侦探 --keywords 赛博朋克    # 初始化小说项目
  python pipeline/run.py run 赛博侦探                       # 执行流水线全流程
  python pipeline/run.py status 赛博侦探                     # 查看项目进度与 Token 消耗
  python pipeline/run.py stats 赛博侦探                      # 小说数据全景与文学工艺指标
  python pipeline/run.py audit 赛博侦探                      # 设定、角色与大纲伏笔一致性审计
  python pipeline/run.py export 赛博侦探 --format all        # 导出 EPUB 电子书、HTML 阅读器、规范 TXT
  python pipeline/run.py kb 戴森球                           # 检索 32 篇科幻方法论知识库
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analytics  # noqa: E402
import audit  # noqa: E402
import doctor  # noqa: E402
import export  # noqa: E402
import kb  # noqa: E402
import llm  # noqa: E402
import stages  # noqa: E402
from stages import Project  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- 终端颜色辅助

def _color(text: str, code: str) -> str:
    # 如果输出支持 ANSI 或不是重定向，添加颜色样式
    if sys.stdout.isatty() or os.environ.get("TERM"):
        return f"\033[{code}m{text}\033[0m"
    return text


def green(text: str) -> str:
    return _color(text, "32")


def red(text: str) -> str:
    return _color(text, "31")


def yellow(text: str) -> str:
    return _color(text, "33")


def cyan(text: str) -> str:
    return _color(text, "36")


def bold(text: str) -> str:
    return _color(text, "1")


# ---------------------------------------------------------------- 命令实现

def cmd_config(args: argparse.Namespace) -> None:
    updates = {}
    for key in ("api_key", "base_url", "model", "temperature", "max_tokens"):
        val = getattr(args, key, None)
        if val is not None:
            updates[key] = val
    if not updates:
        try:
            cfg = llm.load_config(ROOT)
        except Exception:
            cfg = dict(llm.DEFAULTS)
            cfg["api_key"] = "(未设置)"
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return
    llm.save_config(ROOT, updates)
    print(green(f"✓ 配置已保存到 {llm.config_path(ROOT)}"))


def cmd_init(args: argparse.Namespace) -> None:
    proj = Project(ROOT, args.name)
    if proj.exists() and not args.overwrite:
        raise SystemExit(red(f"项目已存在：{proj.cfg_path}（如需重置请加 --overwrite）"))
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
    print(green(f"✓ 项目已创建：{proj.cfg_path}"))
    print(f"  下一步：{cyan('python pipeline/run.py run ' + args.name)}")


def _ensure_api(args: argparse.Namespace) -> dict:
    api = llm.load_config(ROOT)
    if args.dry_run:
        print(yellow(f"[dry-run] 使用模型：{api['model']} @ {api['base_url']}"))
    return api


def cmd_run(args: argparse.Namespace) -> None:
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit(red(f"项目不存在，请先执行：python pipeline/run.py init {args.name}"))
    cfg = proj.config()
    todo = stages.STAGES if args.stages in ("all", None) else [
        s.strip() for s in args.stages.split(",") if s.strip()]
    bad = [s for s in todo if s not in stages.STAGES]
    if bad:
        raise SystemExit(red(f"未知阶段：{','.join(bad)}\n可用阶段：{','.join(stages.STAGES)}"))

    api = None
    if any(s != "assemble" for s in todo):
        api = _ensure_api(args)

    print(cyan(f"▶ 项目《{cfg.get('title')}》 执行流程：{' → '.join(todo)}"))
    for stage in todo:
        label = stages.STAGE_LABEL[stage]
        if stage in ("concept", "world", "characters", "outline"):
            fpath = getattr(proj, f"f_{stage}")()
            if os.path.exists(fpath) and not args.force:
                print(f"• [{label}] 已存在，跳过（--force 可重做）")
                proj.mark(stage, "done")
                continue
        print(f"• [{label}] 生成中…")
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
        except Exception as e:
            proj.mark(stage, "failed")
            print(red(f"✗ [{label}] 失败：{e}"))
            raise SystemExit(1)
        proj.mark(stage, "done")
        print(green(f"  {msg}"))
    print(bold(green("✔ 全部阶段完成！")))


def cmd_status(args: argparse.Namespace) -> None:
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit(red(f"项目不存在：{args.name}"))
    cfg = proj.config()
    st = proj.state()
    target_ch = cfg.get("target_chapters", 20)
    per_w = cfg.get("words_per_chapter", 3000)
    print(bold(f"《{cfg.get('title')}》  {target_ch}章 × {per_w}字（目标约 {target_ch * per_w:,} 字）"))
    print(f"题材关键词：{'、'.join(cfg.get('keywords') or []) or '—'}")
    print("阶段状态：")
    for s in stages.STAGES:
        mark = st.get("stages", {}).get(s, "未开始")
        icon = {"done": green("✓"), "failed": red("✗"), "running": yellow("…")}.get(mark, " ")
        print(f"  {icon} {stages.STAGE_LABEL[s]:<10} {mark}")

    files = proj.list_chapters()
    if files:
        total = sum(stages.word_count(stages.read(p)) for p in files)
        print(f"正文进展：已产出 {bold(str(len(files)))} 章，全书累计 {bold(f'{total:,}')} 字")
    else:
        print("正文进展：尚未生成")

    # 显示 Token 消耗
    tu = st.get("token_usage")
    if tu and tu.get("total_tokens"):
        print(f"Token消耗：输入 {tu.get('prompt_tokens', 0):,} / 输出 {tu.get('completion_tokens', 0):,} / 总计 {tu.get('total_tokens', 0):,}")

    # 显示平均审校评分
    scores = st.get("scores")
    if scores:
        vals = [float(v) for v in scores.values()]
        print(f"审校评分：已审 {len(vals)} 章，平均分 {sum(vals) / len(vals):.1f} / 10.0")


def cmd_stats(args: argparse.Namespace) -> None:
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit(red(f"项目不存在：{args.name}"))
    res = analytics.analyze_project(proj)
    print(analytics.format_stats_report(res))


def cmd_audit(args: argparse.Namespace) -> None:
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit(red(f"项目不存在：{args.name}"))
    res = audit.audit_project(proj)
    print(audit.format_audit_report(res))


def cmd_export(args: argparse.Namespace) -> None:
    proj = Project(ROOT, args.name)
    if not proj.exists():
        raise SystemExit(red(f"项目不存在：{args.name}"))
    fmts = [args.format] if args.format != "all" else ["epub", "html", "txt"]
    print(cyan(f"正在导出《{proj.config().get('title', proj.name)}》..."))
    res = export.export_all(proj, formats=fmts)
    print(green("✔ 导出成功！产物清单："))
    for fmt_name, path in res.items():
        rel = os.path.relpath(path, ROOT)
        size_kb = round(os.path.getsize(path) / 1024, 1)
        print(f"  • [{fmt_name.upper():<4}] {rel} ({size_kb} KB)")


def cmd_doctor(_args: argparse.Namespace) -> None:
    print(doctor.run_doctor(ROOT))


def cmd_kb(args: argparse.Namespace) -> None:
    if not args.keyword:
        for path in kb.list_files(ROOT):
            print(os.path.relpath(path, ROOT))
        return
    hits = kb.search(ROOT, args.keyword, limit=args.limit)
    if not hits:
        print(yellow(f"未在知识库中找到相关条目：{args.keyword}"))
        return
    print(cyan(f"检索到 {len(hits)} 处高相关知识点（已按相关度权重降序排列）：\n"))
    for rel, no, line in hits:
        print(f"  {green(rel)}:{cyan(str(no))} {line[:150]}")


# ---------------------------------------------------------------- 参数解析

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="FutureTxt —— 中文科幻长篇知识库 + 自动化创作流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    # doctor
    d = sub.add_parser("doctor", help="全系统环境、知识库完整性与 API 连通性自检")
    d.set_defaults(func=cmd_doctor)

    # config
    c = sub.add_parser("config", help="配置 LLM API 参数（写入 config.json）")
    c.add_argument("--api-key", help="API Key")
    c.add_argument("--base-url", help="API 基础地址，如 https://api.deepseek.com/v1")
    c.add_argument("--model", help="模型标识，如 deepseek-chat 或 gpt-4o")
    c.add_argument("--temperature", type=float, help="创作温度 (默认 0.8)")
    c.add_argument("--max-tokens", type=int, dest="max_tokens", help="最大输出 Token")
    c.set_defaults(func=cmd_config)

    # init
    i = sub.add_parser("init", help="初始化一部新科幻长篇小说")
    i.add_argument("name", help="项目标识（同时作为目录名）")
    i.add_argument("--title", help="正式书名，默认同项目标识")
    i.add_argument("--keywords", help="题材关键词，逗号分隔，如 '赛博朋克,意识上传,侦探'")
    i.add_argument("--premise", help="一句话故事核心前提（Logline）")
    i.add_argument("--chapters", type=int, default=20, help="目标章节数，默认 20")
    i.add_argument("--words", type=int, default=3000, help="每章期望字数，默认 3000")
    i.add_argument("--pov", default="第三人称有限", help="叙事视角（第三人称有限/第一人称/全知等）")
    i.add_argument("--tone", default="克制、具象、冷峻中有温度", help="文风基调")
    i.add_argument("--audience", default="成人科幻读者", help="目标读者画像")
    i.add_argument("--extra", help="作者补充的特殊设定或硬性要求")
    i.add_argument("--overwrite", action="store_true", help="如项目已存在则强制重置覆盖")
    i.set_defaults(func=cmd_init)

    # run
    r = sub.add_parser("run", help="执行创作流水线")
    r.add_argument("name", help="项目标识")
    r.add_argument("--stages", default="all",
                   help="指定执行的阶段（逗号分隔）：concept,world,characters,outline,draft,review,revise,assemble")
    r.add_argument("--only", help="仅处理指定章节范围，如 3、1-5、1,4,7-9（作用于 draft/review/revise）")
    r.add_argument("--force", action="store_true", help="强制重新生成已有产物")
    r.add_argument("--dry-run", action="store_true", help="仅校验配置与环境，不发起实际生成")
    r.set_defaults(func=cmd_run)

    # status
    s = sub.add_parser("status", help="查看小说项目各阶段完成进度与字数")
    s.add_argument("name", help="项目标识")
    s.set_defaults(func=cmd_status)

    # stats
    st = sub.add_parser("stats", help="全书数据指标分析（字数分布、对白占比、角色聚光灯、阅读时长）")
    st.add_argument("name", help="项目标识")
    st.set_defaults(func=cmd_stats)

    # audit
    a = sub.add_parser("audit", help="设定、角色一致性与大纲伏笔闭环自动化审计")
    a.add_argument("name", help="项目标识")
    a.set_defaults(func=cmd_audit)

    # export
    e = sub.add_parser("export", help="导出出版级电子书（EPUB 3.0 / 离线单文件 HTML 阅读器 / 规范排版 TXT）")
    e.add_argument("name", help="项目标识")
    e.add_argument("--format", choices=["epub", "html", "txt", "all"], default="all",
                   help="导出格式：epub / html / txt / all（默认 all）")
    e.set_defaults(func=cmd_export)

    # kb
    k = sub.add_parser("kb", help="智能检索 32 篇科幻方法论知识库")
    k.add_argument("keyword", nargs="?", help="检索关键词（如 '黑洞'、'曲率'、'冷峻'）")
    k.add_argument("--limit", type=int, default=15, help="返回条目上限，默认 15")
    k.set_defaults(func=cmd_kb)

    return p


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
