"""知识库加载与智能检索器（纯 Python 标准库，零第三方依赖）。

功能：
1. 按流水线阶段加载关联知识模块，支持多模块预算均分，避免先验模块吃光字符额度；
2. 超长文本智能截断（保头保尾，保留关键规则与清单）；
3. 基于轻量 BM25/相关度打分的知识库全文检索；
4. 基于章节主题的动态知识片段检索（轻量动态 RAG）。
"""

from __future__ import annotations

import math
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

KB_DIRNAME = "knowledge"

# 每个流水线阶段需要引用的知识模块（按相对路径子串匹配）
STAGE_MODULES: Dict[str, List[str]] = {
    "concept": ["01-概论", "07-素材与创意"],
    "world": ["01-概论/02", "02-世界观", "03-科学顾问"],
    "characters": ["04-角色", "02-世界观/06"],
    "outline": ["05-情节结构", "07-素材与创意", "01-概论/03"],
    "draft": ["06-文风与叙事", "05-情节结构", "04-角色/03", "02-世界观/02", "08-参考/02"],
    "review": ["08-参考/03", "03-科学顾问"],
    "revise": ["06-文风与叙事", "05-情节结构"],
}

DEFAULT_CAP = 16000  # 单阶段注入知识的总字符上限


def kb_root(root: str) -> str:
    return os.path.join(root, KB_DIRNAME)


def list_files(root: str) -> List[str]:
    """返回 knowledge 目录下全部 .md 文件绝对路径（排序）。"""
    base = kb_root(root)
    out: List[str] = []
    if not os.path.isdir(base):
        return out
    for dirpath, _dirs, files in os.walk(base):
        for name in sorted(files):
            if name.endswith(".md"):
                out.append(os.path.join(dirpath, name))
    out.sort()
    return out


def _clip_preserve_edges(text: str, cap: int) -> str:
    """智能截断单篇文档：保留前 65%（原理定义）与后 35%（清单/速查规则）。"""
    text = (text or "").strip()
    if len(text) <= cap:
        return text
    head_len = int(cap * 0.65)
    tail_len = cap - head_len
    return text[:head_len] + "\n\n…（中间正文略，保留末尾速查规则）…\n\n" + text[-tail_len:]


def load(root: str, keys: Sequence[str], cap: int = DEFAULT_CAP) -> str:
    """读取匹配的知识文件，多模块预算均分，避免前序文件饿死后续科学顾问等核心模块。"""
    all_files = list_files(root)
    if not all_files or not keys:
        return ""

    # 1. 将文件按匹配的 key 分组归类
    groups: List[Tuple[str, List[Tuple[str, str]]]] = []
    seen_paths = set()
    for key in keys:
        matched_in_key = []
        for path in all_files:
            rel = os.path.relpath(path, root).replace("\\", "/")
            if key in rel and path not in seen_paths:
                matched_in_key.append((rel, path))
                seen_paths.add(path)
        if matched_in_key:
            groups.append((key, matched_in_key))

    if not groups:
        return ""

    # 2. 为每个模块组分配字符预算，确保每个知识模块都能获得注入配额
    group_budget = max(int(cap / len(groups)), 800)
    parts: List[str] = []
    total_used = 0

    for _key, group_files in groups:
        remain_total = cap - total_used
        if remain_total <= 400:
            break
        current_group_cap = min(group_budget, remain_total)
        # 为避免单组内文件过多导致严重碎片化，单组最多选取前 4 篇相关文档
        selected_files = group_files[:4]
        file_budget = max(int(current_group_cap / len(selected_files)), 400)

        group_used = 0
        for rel, path in selected_files:
            remain_in_group = current_group_cap - group_used
            if remain_in_group <= 200:
                break
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read().strip()
            except OSError:
                continue

            current_budget = min(file_budget, remain_in_group)
            clipped = _clip_preserve_edges(content, current_budget)
            display_title = rel.replace("knowledge/", "")
            entry = f"### 知识库文档：{display_title}\n{clipped}"
            parts.append(entry)
            group_used += len(entry)

        total_used += group_used

    return "\n\n".join(parts)


def _tokenize(text: str) -> List[str]:
    """简单中文字词切分（汉字二元分词 + 英文/数字词元）。"""
    tokens: List[str] = []
    # 提取英文/数字词
    words = re.findall(r"[A-Za-z0-9_]+", text.lower())
    tokens.extend(words)
    # 提取汉字二元词
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    if len(cjk) == 1:
        tokens.append(cjk[0])
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


def search(root: str, keyword: str, limit: int = 30) -> List[Tuple[str, int, str]]:
    """关键词/短语搜索，基于相关度打分排序，返回 [(相对路径, 行号, 行内容)]。"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    kw_lower = kw.lower()
    kw_tokens = set(_tokenize(kw_lower))
    if not kw_tokens:
        kw_tokens = {kw_lower}

    candidates = []
    for path in list_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as f:
                for no, line in enumerate(f, 1):
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    line_lower = line_clean.lower()
                    score = 0.0
                    # 精确子串匹配赋予高权重
                    if kw_lower in line_lower:
                        score += 10.0 + (5.0 if line_clean.startswith("#") else 0.0)
                    else:
                        # 分词重合打分
                        line_tokens = set(_tokenize(line_lower))
                        overlap = kw_tokens & line_tokens
                        if overlap:
                            score += len(overlap) * 2.0
                    if score > 0:
                        candidates.append((score, rel, no, line_clean))
        except OSError:
            continue

    # 按分数降序排列，分数相同时按路径与行号升序
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [(rel, no, line) for _score, rel, no, line in candidates[:limit]]


def retrieve_snippets(root: str, query: str, cap: int = 4000, max_snippets: int = 5) -> str:
    """按查询动态检索最相关的知识小节（Markdown `##` 或 `###` 段落），用于局部针对性注入。"""
    query_tokens = set(_tokenize(query.lower()))
    if not query_tokens:
        return ""

    sections = []
    for path in list_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        raw_sections = re.split(r"\n(?=##?\s+)", content)
        for sec in raw_sections:
            sec_clean = sec.strip()
            if len(sec_clean) < 60:
                continue
            sec_lower = sec_clean.lower()
            tokens = set(_tokenize(sec_lower))
            overlap = query_tokens & tokens
            if overlap:
                # BM25-lite 打分
                score = len(overlap) / (math.log(len(tokens) + 10) + 1.0)
                sections.append((score, rel, sec_clean))

    sections.sort(key=lambda x: -x[0])
    selected = []
    used = 0
    for _score, rel, sec in sections[:max_snippets]:
        if used + len(sec) > cap:
            break
        display_rel = rel.replace("knowledge/", "")
        selected.append(f"【参考模块：{display_rel}】\n{sec}")
        used += len(sec)

    return "\n\n".join(selected)
