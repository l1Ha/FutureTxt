"""小说全维度数据统计与文学工艺分析器（纯标准库，零第三方依赖）。

分析维度：
1. 字数与篇幅分布（均值、极差、标准差、终端字符柱状图）；
2. 预估阅读时间（默读速度、有声演播时长）；
3. 叙事工艺指标（对白占比、段落均长、信息密度）；
4. 核心角色出场频次与聚光灯分析；
5. 章节审校评分趋势（若已完成审校）。
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple


def _word_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _extract_dialogue_ratio(text: str) -> Tuple[float, int, int]:
    """计算对白字数与对白比例。识别「」、""、“”等引号对。"""
    pattern = re.compile(r"[“「\"].*?[”」\"]", re.S)
    dialogues = pattern.findall(text or "")
    diag_words = sum(_word_count(d) for d in dialogues)
    total = _word_count(text)
    ratio = (diag_words / total) if total > 0 else 0.0
    return ratio, diag_words, total


def _generate_bar_chart(values: List[int], max_width: int = 24) -> List[str]:
    """生成终端字符柱状图。"""
    if not values:
        return []
    max_val = max(values) if max(values) > 0 else 1
    blocks = "  ▂▃▄▅▆▇█"
    lines = []
    for val in values:
        norm = val / max_val
        bar_len = int(norm * max_width)
        bar_str = "█" * bar_len
        lines.append(f"{bar_str:<{max_width}} {val:>5} 字")
    return lines


def analyze_project(proj: Any) -> Dict[str, Any]:
    """对项目进行全维度分析，返回结构化统计字典。"""
    files = proj.list_chapters()
    if not files:
        return {"error": "暂无章节正文"}

    cfg = proj.config()
    chapter_stats: List[Dict[str, Any]] = []
    all_words: List[int] = []
    total_diag_words = 0
    total_words = 0
    total_paragraphs = 0

    # 提取角色表以便分析聚光灯
    char_names: List[str] = []
    char_file = proj.f_characters()
    if os.path.exists(char_file):
        with open(char_file, encoding="utf-8") as f:
            char_text = f.read()
        for m in re.finditer(r"##\s*角色[：:]\s*([^\n\s(/（]+)", char_text):
            name = m.group(1).strip()
            if name and len(name) >= 2 and name not in char_names:
                char_names.append(name)

    char_counts: Dict[str, int] = {name: 0 for name in char_names}

    for path in files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        no_match = re.search(r"chapter_(\d+)", os.path.basename(path))
        ch_num = int(no_match.group(1)) if no_match else 0
        w = _word_count(text)
        all_words.append(w)
        total_words += w

        # 对白比
        d_ratio, d_words, _ = _extract_dialogue_ratio(text)
        total_diag_words += d_words

        # 段落数
        paras = [p.strip() for p in text.splitlines() if p.strip() and not p.startswith("#")]
        total_paragraphs += len(paras)

        # 角色提及统计
        for name in char_names:
            char_counts[name] += text.count(name)

        # 提取审校分数
        score: Optional[float] = None
        rev_path = proj.review_file(ch_num)
        if os.path.exists(rev_path):
            with open(rev_path, encoding="utf-8") as rf:
                rev_text = rf.read()
            sm = re.search(r"(\d+(?:\.\d+)?)\s*/?\s*10", rev_text)
            if sm:
                score = float(sm.group(1))

        # 章节标题
        first_line = ""
        for line in text.splitlines():
            if line.strip().startswith("#"):
                first_line = re.sub(r"^#+\s*", "", line).strip()
                break

        chapter_stats.append({
            "chapter": ch_num,
            "title": first_line or f"第{ch_num}章",
            "words": w,
            "dialogue_ratio": d_ratio,
            "paragraphs": len(paras),
            "score": score,
        })

    # 数学统计
    n = len(all_words)
    avg_words = total_words / n if n else 0
    variance = sum((x - avg_words) ** 2 for x in all_words) / n if n else 0
    std_dev = math.sqrt(variance)
    min_w = min(all_words) if all_words else 0
    max_w = max(all_words) if all_words else 0

    overall_diag_ratio = (total_diag_words / total_words) if total_words else 0.0

    # 预估时长：默读 450 字/分钟，演播 260 字/分钟
    read_mins = round(total_words / 450, 1)
    audio_hours = round(total_words / (260 * 60), 2)

    return {
        "title": cfg.get("title", proj.name),
        "total_chapters": n,
        "total_words": total_words,
        "avg_words": round(avg_words),
        "min_words": min_w,
        "max_words": max_w,
        "std_dev": round(std_dev, 1),
        "dialogue_ratio": round(overall_diag_ratio, 3),
        "paragraphs": total_paragraphs,
        "reading_mins": read_mins,
        "audio_hours": audio_hours,
        "chapters": chapter_stats,
        "character_spotlight": sorted(char_counts.items(), key=lambda x: -x[1]),
    }


def format_stats_report(stats: Dict[str, Any]) -> str:
    """将统计数据格式化为终端易读报表。"""
    if "error" in stats:
        return f"无法生成统计：{stats['error']}"

    lines = []
    lines.append(f"╔{'═' * 58}╗")
    lines.append(f"║ 《{stats['title']}》 小说全景数据与工艺指标分析{' ' * (36 - len(stats['title']) * 2)}║")
    lines.append(f"╠{'═' * 58}╣")
    lines.append(f"║ 规模总量：{stats['total_chapters']:>2} 章 | 总计 {stats['total_words']:,} 字 | 段落共 {stats['paragraphs']:,} 段{' ' * 10}║")
    lines.append(f"║ 章节篇幅：均值 {stats['avg_words']} 字 | 最少 {stats['min_words']} 字 | 最多 {stats['max_words']} 字 | 波动差 ±{stats['std_dev']}║")
    lines.append(f"║ 阅读成本：常人默读约 {stats['reading_mins']} 分钟 | 有声演播约 {stats['audio_hours']} 小时{' ' * 10}║")

    d_ratio = stats["dialogue_ratio"] * 100
    ratio_comment = "叙事沉浸均衡"
    if d_ratio < 20:
        ratio_comment = "说明与叙事偏多，可适当增加对白"
    elif d_ratio > 50:
        ratio_comment = "对话密度较高，节奏明快"
    lines.append(f"║ 对白占比：{d_ratio:.1f}% ({ratio_comment}){' ' * (22 - len(ratio_comment) * 2)}║")
    lines.append(f"╚{'═' * 58}╝")

    # 篇幅分布图
    lines.append("\n【逐章字数与节奏分布图】")
    word_list = [ch["words"] for ch in stats["chapters"]]
    bars = _generate_bar_chart(word_list, max_width=20)
    for ch, bar in zip(stats["chapters"], bars):
        score_str = f" | 审校: {ch['score']:.1f}分" if ch["score"] is not None else ""
        diag_pct = f"对白:{ch['dialogue_ratio'] * 100:.0f}%"
        title_disp = ch["title"][:14]
        lines.append(f"  第{ch['chapter']:02d}章 {title_disp:<14} {bar} ({diag_pct}{score_str})")

    # 角色聚光灯
    if stats.get("character_spotlight"):
        lines.append("\n【核心角色聚光灯（出场与提及频次）】")
        for name, count in stats["character_spotlight"][:8]:
            bar_len = min(int(count / max(stats["character_spotlight"][0][1], 1) * 20), 20)
            lines.append(f"  {name:<6} {'█' * bar_len:<20} 出现 {count} 次")

    return "\n".join(lines)
