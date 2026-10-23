# -*- coding: utf-8 -*-
"""中文章节 → 出版级英文译稿（双语发行支线，纯标准库，复用 llm 客户端）。

主水线（9 阶段）只产中文；本支线把已完成的中文章节翻译为英文，
产出 `chapters_en/chapter_NNN.md`，供 `export --lang en` 出英文版三格式。

- **术语表**：从世界观/角色文档一次性生成「中文 = English」对照表，
  保证全书人名、机构、科技、货币、阶级称谓统一（存 `glossary_en.md`）。
- **代码段保护**：反引号片段（哈希、编号）翻译前后原样还原，绝不改动。
- **章首行规范**：输出 `# Chapter N: <英文标题>`（N 与原章号一致）。
- **英文简介**：`blurb_en.md`（供英文版导出使用），由创作概念译出。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import llm
from stages import Project, chapter_no, clip, read, write, word_count

GLOSSARY_SYSTEM = (
    "你是科幻出版项目的术语管理编辑。从给定的中文世界观与角色设定中提取专有名词的"
    "中英对照表，覆盖：人名、机构/部门、科技/设备、货币与计量、阶级/身份称谓、关键概念。\n"
    "要求：每行一条，格式「中文 = English」；英文用词规范、全书统一、尽量简短；"
    "不超过 40 行；不要任何解释或前后缀。"
)

TRANSLATE_SYSTEM = (
    "你是资深科幻文学译者，负责把中文科幻小说译成出版级英文。硬性要求：\n"
    "1) 忠实原文，不增删情节，不加译者注，不添加任何元信息；\n"
    "2) 首行必须是 Markdown 一级标题，格式 `# Chapter N: <英文标题>`，N 与原章号一致；\n"
    "3) 专有名词严格遵循给定术语表，术语表未覆盖者自行拟定并保持全书一致；\n"
    "4) 文风克制冷峻、具象，符合当代英语科幻出版标准，避免直译腔；\n"
    "5) 反引号代码段（如哈希 `3F9A…C2E7`）原样保留，不翻译、不拆改；\n"
    "6) 使用英文标点与英文对话引号规范。\n"
    "直接输出完整英文章节。"
)

BLURB_SYSTEM = (
    "你是科幻出版编辑。将给定的中文作品简介改写为**出版级英文简介**（blurb）："
    "一段话，120–180 词，突出核心设定与冲突，不剧透结局，不出现中文；"
    "直接输出英文简介正文，不要标题、不要任何前后缀。"
)

_CODE_RE = re.compile(r"`[^`\n]+`")


# ---------------------------------------------------------------- 纯函数（可离线测试）

def chapter_heading(text: str) -> Tuple[int, str]:
    """从中文章节提取 (章号, 标题)；解析失败返回 (0, "")。"""
    m = re.search(r"^#{1,3}\s*第\s*(\d+)\s*章\s*(.*)$", text or "", re.M)
    if not m:
        return 0, ""
    return int(m.group(1)), m.group(2).strip()


def normalize_heading(out: str, n: int, title: str = "") -> str:
    """规范英文章首行为 `# Chapter N: 标题`；无标题则退化为 `# Chapter N`。"""
    out = (out or "").strip()
    lines = out.splitlines()
    head_text = ""
    if lines and lines[0].lstrip().startswith("#"):
        head_text = re.sub(r"^#+\s*", "", lines[0]).strip()
        lines = lines[1:]
    head_text = re.sub(r"^(?:Chapter\s*\d+\s*[:：\-–—.]?\s*)", "", head_text, flags=re.I).strip()
    head_text = head_text or (title or "").strip()
    head = ("# Chapter %d: %s" % (n, head_text)) if head_text else ("# Chapter %d" % n)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join([head, ""] + lines).rstrip() + "\n"


def mask_code(text: str) -> Tuple[str, List[str]]:
    """把反引号代码段替换为占位符，返回 (掩码文本, 片段表)。"""
    spans: List[str] = []

    def repl(m: re.Match) -> str:
        spans.append(m.group(0))
        return "\x00%d\x00" % (len(spans) - 1)

    return _CODE_RE.sub(repl, text or ""), spans


def unmask_code(text: str, spans: List[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text or "")


# ---------------------------------------------------------------- LLM 步骤

def glossary_path(proj: Project) -> str:
    return proj.path("glossary_en.md")


def blurb_path(proj: Project) -> str:
    return proj.path("blurb_en.md")


def build_glossary(proj: Project, api: Dict[str, Any], force: bool = False) -> str:
    """生成/复用中英术语对照表（存 glossary_en.md）。"""
    path = glossary_path(proj)
    if os.path.exists(path) and not force:
        return read(path)
    world = clip(read(proj.f_world()), 7000)
    chars = clip(read(proj.f_characters()), 3000)
    out = llm.chat(
        [{"role": "system", "content": GLOSSARY_SYSTEM},
         {"role": "user", "content":
          "【世界观】\n%s\n\n【角色】\n%s\n\n请输出「中文 = English」术语对照表。" % (world, chars)}],
        api, temperature=0.3, what="英文术语表")
    write(path, out)
    return out


def build_blurb(proj: Project, api: Dict[str, Any], force: bool = False) -> str:
    """生成/复用英文简介（存 blurb_en.md），供英文版导出。"""
    path = blurb_path(proj)
    if os.path.exists(path) and not force:
        return read(path)
    concept = read(proj.f_concept())
    m = re.search(r"##\s*故事前提展开[^\n]*\n([\s\S]*?)(?=\n##|$)", concept)
    src = (m.group(1).strip() if m else "") or proj.config().get("premise", "")
    out = llm.chat(
        [{"role": "system", "content": BLURB_SYSTEM},
         {"role": "user", "content": src}],
        api, temperature=0.6, what="英文简介")
    write(path, out)
    return out


def translate_chapter(api: Dict[str, Any], n: int, title: str, text: str,
                      glossary: str) -> str:
    """翻译单章：代码段保护 → LLM → 还原 → 章首行规范化。"""
    body, spans = mask_code(text)
    user = (
        "【术语表】\n%s\n\n【中文原稿】第 %d 章（章名：%s）\n\n%s\n\n"
        "请输出英文译稿，首行为 `# Chapter %d: <英文标题>`。" % (glossary, n, title, body, n))
    out = llm.chat(
        [{"role": "system", "content": TRANSLATE_SYSTEM},
         {"role": "user", "content": user}],
        api, max_tokens=max(int(api.get("max_tokens", 4096)), 6000),
        what="第%d章英译" % n)
    return normalize_heading(unmask_code(out, spans), n, title)


def translate_book(proj: Project, api: Dict[str, Any],
                   only: Optional[str] = None, force: bool = False) -> str:
    """把中文章节批量译为英文，写入 chapters_en/。返回进度摘要。"""
    chapter_files = proj.list_chapters()
    if not chapter_files:
        raise RuntimeError("项目尚无中文章节，请先执行 draft 阶段生成正文。")

    glossary = build_glossary(proj, api, force=force)
    build_blurb(proj, api, force=force)

    en_dir = proj.path("chapters_en")
    os.makedirs(en_dir, exist_ok=True)

    wanted = set(proj.chapters_range(only)) if only else None
    done: List[str] = []
    skipped: List[int] = []
    for path in chapter_files:
        n = chapter_no(path)
        if wanted is not None and n not in wanted:
            continue
        out_path = os.path.join(en_dir, "chapter_%03d.md" % n)
        if os.path.exists(out_path) and not force:
            skipped.append(n)
            continue
        text = read(path)
        _, title = chapter_heading(text)
        en = translate_chapter(api, n, title, text, glossary)
        write(out_path, en)
        done.append("第%d章 %d词" % (n, word_count(en)))

    parts = []
    if done:
        parts.append("已译 %d 章：%s" % (len(done), "；".join(done)))
    if skipped:
        parts.append("跳过 %d 章（已有译稿，--force 可重译）" % len(skipped))
    parts.append("术语表 %s / 英文简介 %s" % (
        os.path.relpath(glossary_path(proj), proj.root),
        os.path.relpath(blurb_path(proj), proj.root)))
    return "英文译稿完成 → chapters_en/；" + "；".join(parts)
