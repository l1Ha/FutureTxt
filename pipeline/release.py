# -*- coding: utf-8 -*-
"""一键发行：打包 ASCII 附件 + 生成双语说明 + 创建/更新 GitHub Release。

设计要点（来自实际踩坑）：
- **GitHub Release 资产名只接受 ASCII**：中文名会被剥离（`意识纪元.epub` → `default.epub`、
  `地球2200.epub` → `2200.epub`），故附件一律用 `asset_prefix`（拼音）命名；
  前缀优先级：`--prefix` 参数 > project.json 的 `asset_prefix`，两者都没有则明确报错。
- **附件命名**：`<prefix>.<ext>`（中文版）、`<prefix>-EN.<ext>`（英文版）。
- **说明自动生成**：中文简介取净稿 TXT 的【作品简介】，英文简介取 `blurb_en.md`（若有），
  并附「附件-作品对照表」与出版约定。
- **可重入**：标签已存在时改为「覆盖上传附件 + 更新说明」，不会重复建发行。
- 依赖 `gh` CLI（发布用）；`--dry-run` 可在无 gh 环境先本地打包预览。

纯标准库；gh/git 为外部工具，与项目一贯的「git remote 配置」约定一致。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Tuple

from stages import Project, read

ASCII_RE = re.compile(r"^[A-Za-z0-9._-]+$")
TAG_RE = re.compile(r"novels-v(\d+)\.(\d+)$")
FORMATS = ("epub", "html", "txt")


# ---------------------------------------------------------------- 纯函数（可离线测试）

def validate_prefix(prefix: str) -> str:
    """校验 ASCII 附件前缀；非法（含中文/空格等）直接报错。"""
    p = (prefix or "").strip()
    if not p:
        raise ValueError("附件前缀不能为空")
    if not ASCII_RE.match(p):
        raise ValueError("附件前缀只能包含 ASCII 字母/数字/._- ：%r" % prefix)
    return p


def resolve_prefix(proj: Project, override: Optional[str] = None) -> str:
    """确定 ASCII 附件前缀：--prefix > project.json:asset_prefix > 报错。"""
    if override:
        return validate_prefix(override)
    cfg = proj.config()
    stored = cfg.get("asset_prefix") or ""
    if stored:
        return validate_prefix(stored)
    raise ValueError(
        "未指定 ASCII 附件前缀（GitHub 资产名不支持中文，会被剥离成 default.epub）。\n"
        "  用法：python pipeline/run.py release %s --prefix JuanYangJiYuan\n"
        "  或写入 project.json：\"asset_prefix\": \"JuanYangJiYuan\"" % proj.name)


def bump_tag(tags: Sequence[str], default: str = "novels-v1.0") -> str:
    """从既有标签推断下一个版本号：取最大 major，minor 加一；无则用 default。"""
    best: Optional[Tuple[int, int]] = None
    for t in tags:
        m = TAG_RE.search((t or "").strip())
        if not m:
            continue
        cur = (int(m.group(1)), int(m.group(2)))
        if best is None or cur > best:
            best = cur
    if best is None:
        return default
    return "novels-v%d.%d" % (best[0], best[1] + 1)


def asset_names(prefix: str, has_en: bool) -> List[Tuple[str, str]]:
    """返回 [(语言, 文件名)]，如 ('zh', 'JuanYangJiYuan.epub')。"""
    out: List[Tuple[str, str]] = []
    for ext in FORMATS:
        out.append(("zh", "%s.%s" % (prefix, ext)))
    if has_en:
        for ext in FORMATS:
            out.append(("en", "%s-EN.%s" % (prefix, ext)))
    return out


def collect_assets(proj: Project, out_dir: str, prefix: str) -> List[Tuple[str, str, str]]:
    """把 dist/ 与 dist_en/ 的产物复制成 ASCII 附件。返回 [(kind, src, dst)]。"""
    src_dirs = {"zh": proj.path("dist"), "en": proj.path("dist_en")}
    frames = {"zh": "%s.%s", "en": "%s-EN.%s"}
    existing: Dict[str, bool] = {}
    for kind, d in src_dirs.items():
        existing[kind] = os.path.isdir(d) and bool(os.listdir(d))

    os.makedirs(out_dir, exist_ok=True)
    result: List[Tuple[str, str, str]] = []
    for kind, name in asset_names(prefix, existing.get("en", False)):
        if not existing.get(kind):
            continue
        ext = name.rsplit(".", 1)[-1]
        src = None
        for f in os.listdir(src_dirs[kind]):
            if f.lower().endswith("." + ext):
                src = os.path.join(src_dirs[kind], f)
                break
        if not src:
            continue
        dst = os.path.join(out_dir, name)
        shutil.copyfile(src, dst)
        result.append((kind, src, dst))
    return result


def _blurb_zh(proj: Project) -> str:
    """中文简介：优先取净稿 TXT 的【作品简介】，退回创作概念前提。"""
    dist = proj.path("dist")
    if os.path.isdir(dist):
        for f in os.listdir(dist):
            if f.lower().endswith(".txt"):
                txt = read(os.path.join(dist, f))
                m = re.search(r"【作品简介】\n([\s\S]*?)\n=", txt)
                if m:
                    return m.group(1).strip()
    concept = read(proj.f_concept())
    m = re.search(r"##\s*故事前提展开[^\n]*\n([\s\S]*?)(?=\n##|$)", concept)
    if m:
        return m.group(1).strip()
    return proj.config().get("premise", "")


def compose_notes(proj: Project, prefix: str, tag: str) -> str:
    """生成发行说明（有英文版时自动双语对照）。"""
    cfg = proj.config()
    title = cfg.get("title", proj.name)
    files = proj.list_chapters()
    from stages import word_count
    total = sum(word_count(read(f)) for f in files) if files else 0
    has_en = os.path.isdir(proj.path("dist_en")) and bool(os.listdir(proj.path("dist_en")))
    en_blurb = read(proj.path("blurb_en.md")).strip()

    rows = []
    for kind, name in asset_names(prefix, has_en):
        label = "中文版《%s》" % title if kind == "zh" else "English Edition"
        rows.append("| `%s` | %s |" % (name, label))
    mapping = "\n".join(rows)

    parts = [
        "FutureTxt 流水线作品 —— **《%s》**%s。\n" % (title, "中英双语发行" if has_en else "出版净稿"),
        "## 《%s》\n" % title,
        "- %d 章 · %s 字" % (len(files), format(total, ",")),
        "- 题材关键词：%s" % "、".join(cfg.get("keywords") or []) or "-",
        "",
        "### 中文简介\n\n%s\n" % _blurb_zh(proj),
    ]
    if has_en and en_blurb:
        parts.append("### English blurb\n\n%s\n" % en_blurb)
    parts += [
        "## 附件与文件名对照\n",
        "GitHub 仅接受 ASCII 资产名，附件按拼音前缀 `%s` 命名：\n" % prefix,
        "| 附件 | 对应版本 |",
        "|---|---|",
        mapping,
        "",
        "| 格式 | 说明 |",
        "|---|---|",
        "| `.epub` | 推荐：Kindle / 微信读书 / Kobo 等主流阅读器可导入 |",
        "| `.html` | 浏览器双击直接阅读（含侧栏目录与暗色模式） |",
        "| `.txt` | 纯文本，任意设备可读 |",
        "",
        "## 版本说明\n",
        "- **出版净稿**：设定编号锚点（W/C 规则、日常细节、条目标题标签）已自动剥离；"
        "带标记审校版见仓库 `chapters/`、`manuscript/`，审计报告见 `reviews/`。",
        "- 导出即净化：`python pipeline/run.py export %s --format all%s`。"
        % (proj.name, " --lang en" if has_en else ""),
        "- 本发行由 `python pipeline/run.py release %s` 生成（标签 `%s`）。" % (proj.name, tag),
    ]
    return "\n".join(x for x in parts if x is not None) + "\n"


# ---------------------------------------------------------------- gh 交互

def _gh(args: Sequence[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(["gh"] + list(args), capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def gh_available() -> bool:
    rc, _, _ = _gh(["--version"])
    return rc == 0


def existing_tags(repo: Optional[str]) -> List[str]:
    args = ["release", "list", "--limit", "100", "--json", "tagName", "-q", ".[].tagName"]
    if repo:
        args += ["--repo", repo]
    rc, out, _ = _gh(args)
    if rc != 0:
        return []
    return [t.strip() for t in out.splitlines() if t.strip()]


def publish(tag: str, title: str, notes_file: str, assets: Sequence[str],
            repo: Optional[str], target: str = "main") -> str:
    """创建或更新发行（标签已存在则覆盖附件并更新说明）。返回发行 URL。"""
    base = ["--repo", repo] if repo else []
    if tag in existing_tags(repo):
        rc, out, err = _gh(["release", "upload", tag] + list(assets) + ["--clobber"] + base)
        if rc != 0:
            raise RuntimeError("覆盖上传附件失败：%s" % err)
        rc, out, err = _gh(["release", "edit", tag, "--title", title,
                            "--notes-file", notes_file] + base)
        if rc != 0:
            raise RuntimeError("更新发行说明失败：%s" % err)
    else:
        rc, out, err = _gh(["release", "create", tag, "--title", title,
                            "--notes-file", notes_file, "--target", target]
                           + list(assets) + base)
        if rc != 0:
            raise RuntimeError("创建发行失败：%s" % err)
    rc, out, _ = _gh(["release", "view", tag, "--json", "url", "-q", ".url"] + base)
    return out or "(未取到 URL)"


def verify(tag: str, repo: Optional[str]) -> List[Tuple[str, float]]:
    """回读发行资产，校验名称全为 ASCII。返回 [(name, KB)]。"""
    base = ["--repo", repo] if repo else []
    rc, out, err = _gh(["release", "view", tag, "--json", "assets"] + base)
    if rc != 0:
        raise RuntimeError("回读发行失败：%s" % err)
    try:
        data = json.loads(out or "{}")
    except ValueError:
        raise RuntimeError("回读发行返回非 JSON：%s" % out[:120])
    items: List[Tuple[str, float]] = []
    for a in (data or {}).get("assets", []):
        name = a.get("name", "")
        if not ASCII_RE.match(name):
            raise RuntimeError("资产名不是 ASCII（会被 GitHub 剥离）：%r" % name)
        items.append((name, round(int(a.get("size", 0)) / 1024, 1)))
    return items


def run_release(proj: Project, tag: Optional[str] = None, prefix: Optional[str] = None,
                title: Optional[str] = None, repo: Optional[str] = None,
                dry_run: bool = False, target: str = "main",
                out_dir: Optional[str] = None) -> str:
    """发行编排：解析前缀 → 打包附件 → 生成说明 → 建/更新发行 → 校验。"""
    pref = resolve_prefix(proj, prefix)
    cfg = proj.config()
    book = cfg.get("title", proj.name)

    if not dry_run and not gh_available():
        raise RuntimeError("未检测到 gh CLI（发布需要它）：https://cli.github.com/")

    has_en = os.path.isdir(proj.path("dist_en")) and bool(os.listdir(proj.path("dist_en")))
    tag = tag or bump_tag(existing_tags(repo))
    title = title or "小说发行 %s ·《%s》%s" % (
        tag.replace("novels-", ""), book, "中英双语" if has_en else "出版净稿")
    out_dir = out_dir or proj.path("release_build")
    notes_file = os.path.join(out_dir, "release_notes.md")

    assets = collect_assets(proj, out_dir, pref)
    if not assets:
        raise RuntimeError("未找到可发行的产物：请先 `export %s --format all`（英文版还需 translate + export --lang en）" % proj.name)
    with open(notes_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(compose_notes(proj, pref, tag))

    lines = ["【发行打包】前缀 %s，标签 %s" % (pref, tag)]
    for kind, src, dst in assets:
        lines.append("  %-3s %-26s ← %s (%.1f KB)"
                     % (kind, os.path.basename(dst), os.path.relpath(src, proj.root),
                        os.path.getsize(dst) / 1024))
    lines.append("  说明：%s" % os.path.relpath(notes_file, proj.root))

    if dry_run:
        lines.append("【dry-run】未发布。去掉 --dry-run 即创建/更新发行。")
        return "\n".join(lines)

    url = publish(tag, title, notes_file, [d for _, _, d in assets], repo, target)
    items = verify(tag, repo)
    lines.append("【已发布】%s" % url)
    lines.append("资产校验（全 ASCII）：%d 件" % len(items))
    for name, kb in sorted(items):
        lines.append("  %-26s %7.1f KB" % (name, kb))
    return "\n".join(lines)
