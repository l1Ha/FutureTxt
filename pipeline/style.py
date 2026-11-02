# -*- coding: utf-8 -*-
"""文风体检器（确定性、零 API 成本、纯标准库）。

为什么需要它：审校模型能判断"好不好"，但对**可计数的坏习惯**并不敏感——
陈词滥调、AI 腔对举句、解释性旁白、超长句、自我重复、副词堆积。
这些恰恰是长时间跑模型后最容易出现的"平均文风"。

本模块只做三件事：
1. 统计可量化指标（句长/段长/对白比/虚词密度/高频四字串）；
2. 标出高置信度的套话与 AI 腔句式（附行号与上下文）；
3. 输出可读报告与可注入提示词的紧凑摘要。

**不改正文、不判优劣、不替代审校**：所有命中都只是"请人工看一眼"的线索。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 词表

# 高置信度套话：命中即列出（按类别提示，不直接判错）
CLICHES: Dict[str, str] = {
    # 环境 / 天气
    "空气仿佛凝固": "环境套话",
    "空气瞬间凝固": "环境套话",
    "空气凝固": "环境套话",
    "时间仿佛静止": "环境套话",
    "时间静止": "环境套话",
    "落针可闻": "环境套话",
    "鸦雀无声": "环境套话",
    "仿佛整个世界都安静": "环境套话",
    # 身体 / 情绪
    "心中一紧": "身体套话",
    "心头一紧": "身体套话",
    "心中一沉": "身体套话",
    "心头一沉": "身体套话",
    "五味杂陈": "情绪套话",
    "百感交集": "情绪套话",
    "思绪万千": "情绪套话",
    "心乱如麻": "情绪套话",
    "泪水夺眶而出": "情绪套话",
    "泪如雨下": "情绪套话",
    "泪流满面": "情绪套话",
    "眼眶湿润": "情绪套话",
    # 动作 / 表情
    "深吸一口气": "动作套话",
    "深吸了一口气": "动作套话",
    "缓缓睁开眼睛": "动作套话",
    "嘴角勾起": "表情套话",
    "嘴角扬起": "表情套话",
    "嘴角微微上扬": "表情套话",
    "露出一丝微笑": "表情套话",
    "露出一抹": "表情套话",
    "眼中闪过": "表情套话",
    "眼神复杂": "表情套话",
    "意味深长": "表情套话",
    "若有所思": "表情套话",
    "若有所失": "表情套话",
    "不由自主": "动作套话",
    "情不自禁": "动作套话",
    # 比喻
    "如潮水般": "比喻套话",
    "如洪水般": "比喻套话",
    "铺天盖地": "比喻套话",
    "排山倒海": "比喻套话",
    "像一把刀": "比喻套话",
    "像一记重锤": "比喻套话",
    "刺入心脏": "比喻套话",
    # 主题 / 时间 / 解释
    "命运的齿轮": "主题套话",
    "时代的洪流": "主题套话",
    "历史的尘埃": "主题套话",
    "不知过了多久": "时间套话",
    "不知从何时起": "时间套话",
    "说不清道不明": "解释套话",
    "无法用语言形容": "解释套话",
    "仿佛在诉说": "拟人套话",
    "仿佛在告诉他": "拟人套话",
}

# 少数套话会作为更长词语的一部分出现（如「长时间静止」「一段时间静止」），命中前先排除
CLICHE_PREFIX_EXCLUDE: Dict[str, Sequence[str]] = {
    "时间静止": ("长", "段"),
    "空气凝固": (),
}

# AI 腔句式（正则，标签）
AI_TEMPLATES: Sequence[Tuple[str, str]] = (
    (r"不是[^，。！？\n]{1,24}，?\s*而是", "对举句式「不是…而是…」"),
    (r"与其说[^，。！？\n]{1,24}，?\s*不如说", "对举句式「与其说…不如说…」"),
    (r"(?:他|她|它|我|你)(?:终于|这才|忽然|突然)?(?:明白|意识到|懂了|醒悟)[了，,。]", "解释性旁白「他明白了」"),
    (r"这(?:一切)?(?:意味着|说明|表示)", "解释性旁白「这意味着」"),
    (r"换句话(?:说|讲)", "解释性旁白「换句话说」"),
    (r"也就是(?:说|讲)", "解释性旁白「也就是说」"),
    (r"不(?:难)?(?:看出|发现)", "解释性旁白「不难看出」"),
    (r"事实证明", "解释性旁白「事实证明」"),
    (r"一种[^，。！？\n]{1,12}的(?:感觉|情绪|东西|力量|存在|味道)", "抽象兜底「一种…的感觉」"),
    (r"某种[^，。！？\n]{1,10}", "模糊限定「某种…」"),
    (r"仿佛[^，。！？\n]{0,20}(?:一般|一样|似的)", "明喻套话「仿佛…一样」"),
    (r"像[^，。！？\n]{1,20}(?:一样|一般|似的)", "明喻套话「像…一样」"),
    (r"在[^，。！？\n]{1,20}的(?:作用下|影响下|背景下)", "背景套话「在…背景下」"),
    (r"让[^，。！？\n]{1,20}变得", "使动套话「让…变得…」"),
    (r"被[^，。！？\n]{1,20}所", "被动套话「被…所…」"),
)

# 虚词 / 口头禅：不逐条报，按密度报
TIC_WORDS: Sequence[str] = (
    "仿佛", "似乎", "好像", "某种", "一种",
    "微微", "缓缓", "轻轻", "静静", "默默", "悄悄",
    "淡淡", "冷冷", "深深", "狠狠", "渐渐", "慢慢",
    "突然", "忽然", "终于", "竟然", "居然",
    "不由得", "不由自主", "下意识", "若有所思", "意味深长",
)

# 高频四字串过滤：含这些常用字的多半是语法碎片，不作为"口头禅"报告
NGRAM_STOP_CHARS = set("的了着过是在有和与就都也而及其之这那我你他她它们一个不没很更最又还从被把让给对向于为以所")

LONG_SENTENCE = 50          # 汉字数；超过即"长句"
VERY_LONG_PARAGRAPH = 300   # 非空白字符数
DUP_SENTENCE_MIN = 14       # 重复句最短长度（归一化后）
DUP_OPENING_LEN = 8         # 段首取样长度
NGRAM_SIZE = 4
TRAIL_AFTER_END = 150       # 完结标记之后仍有的正文长度（超过即疑似"双结尾"）
CHAPTER_SIM_MIN = 0.20      # 两章 5 字滑窗重叠度（含盖率）达到即"高度相似"
SHINGLE_SIZE = 5

END_MARKERS: Sequence[str] = (
    "（全文完）", "(全文完)", "【全文完】", "——全文完——", "（完）", "(完)",
)


# ---------------------------------------------------------------- 基础工具

def _nonspace_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


_PUNCT_RE = re.compile(r"[\s。！？!?…，、；：“”‘’\"'「」『』（）()《》〈〉—\-·.,!?;:]")


def _prose_len(text: str) -> int:
    """句/段长度只算文字，不算标点（更接近朗读时的实际长度）。"""
    return len(_PUNCT_RE.sub("", text or ""))


def _body_lines(text: str) -> List[Tuple[int, str]]:
    """返回 (行号, 去空白行) 的正文行，跳过 Markdown 标题。"""
    out = []
    for no, line in enumerate((text or "").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append((no, s))
    return out


def _context(text: str, start: int, end: int, width: int = 12) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    return ("…" if a > 0 else "") + text[a:b] + ("…" if b < len(text) else "")


def _normalize(text: str) -> str:
    """去掉标点/空白，只保留汉字、字母、数字，用于重复检测。"""
    return re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9]", "", text or "")


def _sentence_list(text: str) -> List[str]:
    body = re.sub(r"^#.*$", "", text or "", flags=re.M)
    return [s.strip() for s in re.findall(r"[^。！？!?…\n]+[。！？!?…]*", body)
            if s.strip()]


# ---------------------------------------------------------------- 单元检测

def find_cliches(text: str) -> List[Dict[str, Any]]:
    """高置信度套话命中（同一行内长词优先，避免重复计数）。"""
    hits: List[Dict[str, Any]] = []
    phrases = sorted(CLICHES, key=len, reverse=True)
    for line_no, line in _body_lines(text):
        occupied: List[Tuple[int, int]] = []
        for phrase in phrases:
            start = 0
            while True:
                i = line.find(phrase, start)
                if i < 0:
                    break
                j = i + len(phrase)
                bad_prefix = tuple(CLICHE_PREFIX_EXCLUDE.get(phrase) or ())
                if bad_prefix and any(line[:i].endswith(p) for p in bad_prefix):
                    start = j
                    continue
                if not any(i < e and s < j for s, e in occupied):
                    occupied.append((i, j))
                    hits.append({
                        "phrase": phrase,
                        "category": CLICHES[phrase],
                        "line": line_no,
                        "context": _context(line, i, j),
                    })
                start = j
    return hits


def find_ai_templates(text: str) -> List[Dict[str, Any]]:
    """AI 腔句式命中（逐行匹配，同一位置只保留首个标签）。"""
    hits: List[Dict[str, Any]] = []
    compiled = [(re.compile(p), label) for p, label in AI_TEMPLATES]
    for line_no, line in _body_lines(text):
        seen: List[Tuple[int, int]] = []
        for rx, label in compiled:
            for m in rx.finditer(line):
                span = (m.start(), m.end())
                if any(span[0] < e and s < span[1] for s, e in seen):
                    continue
                seen.append(span)
                hits.append({
                    "label": label,
                    "line": line_no,
                    "text": m.group(0)[:40],
                    "context": _context(line, span[0], span[1]),
                })
    return hits


def count_tic_words(text: str) -> List[Dict[str, Any]]:
    chars = max(_nonspace_len(text), 1)
    out = []
    for word in TIC_WORDS:
        n = (text or "").count(word)
        if n:
            out.append({"word": word, "count": n,
                        "per_1000": round(n * 1000.0 / chars, 1)})
    out.sort(key=lambda x: (-x["count"], x["word"]))
    return out


def sentence_stats(text: str) -> Dict[str, Any]:
    sents = _sentence_list(text)
    lens = [_prose_len(s) for s in sents]
    long_sents = [(s, n) for s, n in zip(sents, lens) if n >= LONG_SENTENCE]
    long_sents.sort(key=lambda x: -x[1])
    total = sum(lens)
    return {
        "count": len(lens),
        "avg": round(total / len(lens), 1) if lens else 0.0,
        "max": max(lens) if lens else 0,
        "long_count": len(long_sents),
        "long_ratio": round(len(long_sents) / len(lens), 3) if lens else 0.0,
        "longest": [{"text": s[:80], "chars": n} for s, n in long_sents[:3]],
    }


def paragraph_stats(text: str) -> Dict[str, Any]:
    paras = [s for _no, s in _body_lines(text)]
    lens = [_prose_len(p) for p in paras]
    return {
        "count": len(lens),
        "avg": round(sum(lens) / len(lens), 1) if lens else 0.0,
        "max": max(lens) if lens else 0,
        "over_300": sum(1 for n in lens if n >= VERY_LONG_PARAGRAPH),
    }


def dialogue_ratio(text: str) -> float:
    body = re.sub(r"^#.*$", "", text or "", flags=re.M)
    quoted = re.findall(r"[“「]([^”」]*)[”」]", body)
    d = sum(_prose_len(x) for x in quoted)
    total = _prose_len(body)
    return round(d / total, 3) if total else 0.0


def find_dup_sentences(chapters: Sequence[Tuple[int, str]]) -> List[Dict[str, Any]]:
    """跨章/章内重复整句（归一化后 ≥14 字）。"""
    groups: Dict[str, Dict[str, Any]] = {}
    for ch, text in chapters:
        for sent in _sentence_list(text):
            norm = _normalize(sent)
            if len(norm) < DUP_SENTENCE_MIN:
                continue
            item = groups.setdefault(norm, {"sentence": sent.strip(), "chapters": [], "count": 0})
            item["chapters"].append(ch)
            item["count"] += 1
    out = []
    for item in groups.values():
        chs = sorted(set(item["chapters"]))
        if item["count"] >= 2:
            out.append({
                "sentence": item["sentence"][:80],
                "chapters": chs,
                "count": item["count"],
                "same_chapter": len(chs) == 1,
            })
    out.sort(key=lambda x: (-x["count"], -len(x["sentence"])))
    return out


def find_dup_openings(chapters: Sequence[Tuple[int, str]]) -> List[Dict[str, Any]]:
    """重复段首（归一化后取前 8 字，出现 ≥3 次）。"""
    groups: Dict[str, Dict[str, Any]] = {}
    for ch, text in chapters:
        for _no, line in _body_lines(text):
            norm = _normalize(line)
            if len(norm) < DUP_OPENING_LEN:
                continue
            key = norm[:DUP_OPENING_LEN]
            item = groups.setdefault(key, {"opening": line[:16], "chapters": [], "count": 0})
            item["chapters"].append(ch)
            item["count"] += 1
    out = [dict(opening=v["opening"], chapters=sorted(set(v["chapters"])), count=v["count"])
           for v in groups.values() if v["count"] >= 3]
    out.sort(key=lambda x: -x["count"])
    return out


def find_end_markers(text: str) -> Dict[str, Any]:
    """完结标记检测：出现次数 + 最后一次标记之后的正文长度（双结尾线索）。"""
    body = text or ""
    positions: List[Tuple[str, int]] = []
    for marker in END_MARKERS:
        start = 0
        while True:
            i = body.find(marker, start)
            if i < 0:
                break
            positions.append((marker, i))
            start = i + len(marker)
    positions.sort(key=lambda x: x[1])
    if not positions:
        return {"count": 0, "markers": [], "trail_chars": 0}
    # 取"任意完结标记之后"的最长正文：多重收尾或闸门在完结后继续续写都会被标出
    trail = max(_prose_len(body[i + len(m):]) for m, i in positions)
    return {
        "count": len(positions),
        "markers": sorted({m for m, _ in positions}),
        "trail_chars": trail,
    }


def _shingle_set(text: str) -> set:
    """章节正文的 5 字滑窗集合（先归一化为纯文字）。"""
    norm = _normalize(text)
    if len(norm) < SHINGLE_SIZE:
        return set()
    return {norm[i:i + SHINGLE_SIZE] for i in range(len(norm) - SHINGLE_SIZE + 1)}


def find_similar_chapters(chapters: Sequence[Tuple[int, str]],
                          threshold: float = CHAPTER_SIM_MIN) -> List[Dict[str, Any]]:
    """跨章高度相似检测：改头换面的重复章（如第 5 章是第 4 章的换名重写）。

    用重叠系数 |A∩B|/min(|A|,|B|)：只要一章的大部分内容出现在另一章里即命中，
    对"复制后局部改写"的稿子比 Jaccard 更敏感。
    """
    shingles = [(n, _shingle_set(t)) for n, t in chapters]
    out: List[Dict[str, Any]] = []
    for i in range(len(shingles)):
        ni, si = shingles[i]
        if not si:
            continue
        for j in range(i + 1, len(shingles)):
            nj, sj = shingles[j]
            if not sj:
                continue
            inter = len(si & sj)
            cover = inter / min(len(si), len(sj))
            if cover >= threshold:
                out.append({"a": ni, "b": nj, "cover": round(cover, 3),
                            "shared": inter, "smaller": min(len(si), len(sj))})
    out.sort(key=lambda x: -x["cover"])
    return out


def top_ngrams(text: str, min_count: int = 5, limit: int = 8) -> List[Dict[str, Any]]:
    """高频四字串（可能是设定术语，也可能是口头禅；仅作线索）。"""
    counter: Dict[str, int] = {}
    for run in re.findall(r"[\u4e00-\u9fff]{%d,}" % NGRAM_SIZE, text or ""):
        for i in range(len(run) - NGRAM_SIZE + 1):
            gram = run[i:i + NGRAM_SIZE]
            if any(ch in NGRAM_STOP_CHARS for ch in gram):
                continue
            counter[gram] = counter.get(gram, 0) + 1
    items = [{"phrase": k, "count": v} for k, v in counter.items() if v >= min_count]
    items.sort(key=lambda x: (-x["count"], x["phrase"]))
    return items[:limit]


# ---------------------------------------------------------------- 汇总

def analyze_text(text: str) -> Dict[str, Any]:
    """单章/单篇体检。"""
    return {
        "words": _nonspace_len(text),
        "dialogue_ratio": dialogue_ratio(text),
        "sentences": sentence_stats(text),
        "paragraphs": paragraph_stats(text),
        "cliche_hits": find_cliches(text),
        "template_hits": find_ai_templates(text),
        "tic_words": count_tic_words(text),
        "top_ngrams": top_ngrams(text),
        "end_markers": find_end_markers(text),
    }


def _score(res: Dict[str, Any]) -> Tuple[int, str]:
    cliche = len(res["cliche_hits"])
    templates = len(res["template_hits"])
    long_ratio = res["sentences"]["long_ratio"]
    tic_total = sum(t["count"] for t in res["tic_words"])
    tic_density = tic_total * 1000.0 / max(res["words"], 1)
    dup_s = len(res["dup_sentences"])
    dup_o = len(res["dup_openings"])
    bad_ends = len(res.get("end_marker_flags") or [])
    sim_pairs = len(res.get("similar_chapters") or [])

    score = 100.0
    score -= min(30, cliche * 3)
    score -= min(22, templates * 2)
    score -= min(16, max(0.0, long_ratio * 100 - 8) * 0.8)
    score -= min(12, max(0.0, tic_density - 10) * 1.2)
    score -= min(10, dup_s * 2)
    score -= min(8, dup_o * 1.5)
    score -= min(15, bad_ends * 8)    # 多重收尾/完结后仍在正文：结构性缺陷
    score -= min(18, sim_pairs * 9)   # 跨章高度相似：结构性缺陷（复制章）
    score = max(0, int(round(score)))
    grade = "A" if score >= 90 else ("B" if score >= 80 else ("C" if score >= 70 else "D"))
    return score, grade


def analyze_project(proj: Any, chapter: Optional[int] = None) -> Dict[str, Any]:
    """全书（或指定一章）体检。"""
    cfg = proj.config()
    files = proj.list_chapters()
    chapters: List[Dict[str, Any]] = []
    chapter_texts: List[Tuple[int, str]] = []
    for path in files:
        m = re.search(r"chapter_(\d+)", os.path.basename(path))
        n = int(m.group(1)) if m else len(chapters) + 1
        if chapter is not None and n != chapter:
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        item = analyze_text(text)
        item["chapter"] = n
        title = ""
        for line in text.splitlines():
            if line.strip().startswith("#"):
                title = re.sub(r"^#+\s*", "", line).strip()
                break
        item["title"] = title or ("第%d章" % n)
        chapters.append(item)
        chapter_texts.append((n, text))

    total_words = sum(c["words"] for c in chapters)
    dlg_words = sum(c["dialogue_ratio"] * c["words"] for c in chapters)
    total_sent = sum(c["sentences"]["count"] for c in chapters)
    total_long = sum(c["sentences"]["long_count"] for c in chapters)
    total_para = sum(c["paragraphs"]["count"] for c in chapters)
    para_weighted = sum(c["paragraphs"]["avg"] * c["paragraphs"]["count"] for c in chapters)

    res: Dict[str, Any] = {
        "title": cfg.get("title", proj.name),
        "form": "short" if str(cfg.get("work_type", "novel")).lower() == "short" else "novel",
        "chapters": chapters,
        "words": total_words,
        "total_words": total_words,
        "dialogue_ratio": round(dlg_words / total_words, 3) if total_words else 0.0,
        "sentences": {
            "count": total_sent,
            "avg": round(sum(c["sentences"]["avg"] * c["sentences"]["count"] for c in chapters)
                         / total_sent, 1) if total_sent else 0.0,
            "max": max((c["sentences"]["max"] for c in chapters), default=0),
            "long_count": total_long,
            "long_ratio": round(total_long / total_sent, 3) if total_sent else 0.0,
            "longest": sorted(
                (dict(item, chapter=c["chapter"])
                 for c in chapters for item in c["sentences"]["longest"]),
                key=lambda x: -x["chars"])[:3],
        },
        "paragraphs": {
            "count": total_para,
            "avg": round(para_weighted / total_para, 1) if total_para else 0.0,
            "max": max((c["paragraphs"]["max"] for c in chapters), default=0),
            "over_300": sum(c["paragraphs"]["over_300"] for c in chapters),
        },
        "cliche_hits": [],
        "template_hits": [],
        "tic_words": [],
        "top_ngrams": top_ngrams("\n".join(t for _n, t in chapter_texts)),
        "dup_sentences": find_dup_sentences(chapter_texts),
        "dup_openings": find_dup_openings(chapter_texts),
        "end_marker_flags": [],
        "similar_chapters": find_similar_chapters(chapter_texts),
    }
    for c in chapters:
        em = c.get("end_markers") or {}
        if em.get("count", 0) >= 2 or em.get("trail_chars", 0) > TRAIL_AFTER_END:
            res["end_marker_flags"].append({
                "chapter": c["chapter"],
                "count": em.get("count", 0),
                "trail_chars": em.get("trail_chars", 0),
                "markers": em.get("markers", []),
            })
    for c in chapters:
        for h in c["cliche_hits"]:
            res["cliche_hits"].append(dict(h, chapter=c["chapter"]))
        for h in c["template_hits"]:
            res["template_hits"].append(dict(h, chapter=c["chapter"]))
    tic: Dict[str, int] = {}
    for c in chapters:
        for t in c["tic_words"]:
            tic[t["word"]] = tic.get(t["word"], 0) + t["count"]
    chars = max(total_words, 1)
    res["tic_words"] = sorted(
        ({"word": k, "count": v, "per_1000": round(v * 1000.0 / chars, 1)}
         for k, v in tic.items()), key=lambda x: (-x["count"], x["word"]))
    res["score"], res["grade"] = _score(res)
    return res


# ---------------------------------------------------------------- 报告

def _hit_line(hit: Dict[str, Any]) -> str:
    where = "第%d章" % hit["chapter"] if hit.get("chapter") else ""
    return "%s第%d行「%s」%s" % (
        (where + " ") if where else "", hit["line"], hit["phrase"],
        "（%s）" % hit["category"])


def format_report(res: Dict[str, Any], max_items: int = 12) -> str:
    if not res.get("chapters"):
        return "未找到章节正文，无法体检。"

    lines: List[str] = []
    lines.append("《%s》文风体检" % res["title"])
    lines.append("━" * 52)
    lines.append("规模：%s 章 / %s 字 / 对白 %.1f%%" % (
        len(res["chapters"]), format(res["total_words"], ","), res["dialogue_ratio"] * 100))
    s = res["sentences"]
    lines.append("句长：均 %.1f 字，最长 %d 字；≥%d 字长句 %d 处（%.1f%%）" % (
        s["avg"], s["max"], LONG_SENTENCE, s["long_count"], s["long_ratio"] * 100))
    p = res["paragraphs"]
    lines.append("段长：均 %.1f 字，最长 %d 字；≥%d 字长段 %d 段" % (
        p["avg"], p["max"], VERY_LONG_PARAGRAPH, p["over_300"]))
    lines.append("体检分：%d / 100（%s）" % (res["score"], res["grade"]))
    lines.append("")

    if len(res["chapters"]) > 1:
        lines.append("【逐章】")
        for c in res["chapters"]:
            lines.append("  第%02d章 %-18s %6s字 句均%5.1f 对白%4.0f%% 套话%d AI腔%d" % (
                c["chapter"], c["title"][:18], format(c["words"], ","),
                c["sentences"]["avg"], c["dialogue_ratio"] * 100,
                len(c["cliche_hits"]), len(c["template_hits"])))
        lines.append("")

    sim_pairs = res.get("similar_chapters") or []
    if sim_pairs:
        lines.append("【高】跨章高度相似 %d 对（疑似复制章/换名重写）" % len(sim_pairs))
        for pair in sim_pairs[:max_items]:
            lines.append("  第%d章 vs 第%d章：重叠 %.0f%%（较小章 %d 个滑窗中 %d 个重复）" % (
                pair["a"], pair["b"], pair["cover"] * 100, pair["smaller"], pair["shared"]))
        lines.append("")

    end_flags = res.get("end_marker_flags") or []
    if end_flags:
        lines.append("【高】收尾异常 %d 章（多重「全文完」或完结后仍有正文）" % len(end_flags))
        for f in end_flags[:max_items]:
            detail = "标记 %d 个" % f["count"]
            if f["trail_chars"] > TRAIL_AFTER_END:
                detail += "，标记后仍有 %d 字" % f["trail_chars"]
            lines.append("  第%d章：%s（可能是字数闸门在完结后继续续写）" % (f["chapter"], detail))
        lines.append("")

    cliches = res["cliche_hits"]
    if cliches:
        lines.append("【高】陈词滥调 %d 处" % len(cliches))
        for h in cliches[:max_items]:
            lines.append("  " + _hit_line(h) + "  … " + h["context"])
        if len(cliches) > max_items:
            lines.append("  … 另有 %d 处" % (len(cliches) - max_items))
        lines.append("")

    templates = res["template_hits"]
    if templates:
        by_label: Dict[str, int] = {}
        for h in templates:
            by_label[h["label"]] = by_label.get(h["label"], 0) + 1
        lines.append("【中】AI 腔句式 %d 处" % len(templates))
        for label, n in sorted(by_label.items(), key=lambda x: -x[1]):
            lines.append("  %s × %d" % (label, n))
        for h in templates[:min(max_items, 6)]:
            lines.append("    第%d章 第%d行「%s」" % (h["chapter"], h["line"], h["text"]))
        lines.append("")

    tics = [t for t in res["tic_words"] if t["count"] >= 4 or t["per_1000"] >= 8]
    if tics:
        lines.append("【中】高频虚词/口头禅")
        lines.append("  " + "、".join("%s×%d（%.1f/千字）" % (t["word"], t["count"], t["per_1000"])
                                     for t in tics[:10]))
        lines.append("")

    if s.get("longest"):
        lines.append("【中】最长句（≥%d 字）" % LONG_SENTENCE)
        for item in s["longest"]:
            where = "第%d章 " % item["chapter"] if item.get("chapter") else ""
            lines.append("  %s%d 字：%s…" % (where, item["chars"], item["text"]))
        lines.append("")

    dups = res["dup_sentences"]
    if dups:
        lines.append("【中】重复整句 %d 组" % len(dups))
        for d in dups[:6]:
            scope = "同章" if d["same_chapter"] else "第%s章" % "、".join(str(x) for x in d["chapters"])
            lines.append("  ×%d（%s）%s…" % (d["count"], scope, d["sentence"][:46]))
        lines.append("")

    openings = res["dup_openings"]
    if openings:
        lines.append("【低】重复段首 %d 组" % len(openings))
        for o in openings[:6]:
            lines.append("  ×%d（第%s章）%s…" % (o["count"], "、".join(str(x) for x in o["chapters"]),
                                              o["opening"]))
        lines.append("")

    ngrams = res["top_ngrams"]
    if ngrams:
        lines.append("【低】高频四字串（术语或口头禅，请人工判断）")
        lines.append("  " + "、".join("%s×%d" % (g["phrase"], g["count"]) for g in ngrams))
        lines.append("")

    if not (cliches or templates or dups or openings or end_flags or sim_pairs):
        lines.append("✔ 未发现高置信度套话、AI 腔、重复句、相似章或收尾异常。")
        lines.append("")

    lines.append("【建议】")
    if sim_pairs:
        lines.append("  · 相似章优先重写：保留其中信息量更大的一章，另一章换成新场景或新代价。")
    if end_flags:
        lines.append("  · 收尾异常优先处理：删掉完结标记之后的续写，或整体只保留一套结尾。")
    if cliches:
        lines.append("  · 套话优先换成**这个人物此刻的具体动作/感官**，不要换同义套话。")
    if templates:
        lines.append("  · 删掉「不是…而是…」「他明白了」这类替读者总结的句子，让动作自己说话。")
    if s["long_ratio"] > 0.08:
        lines.append("  · 长句占比偏高：在转折处断句，一句只做一件事。")
    if p["over_300"]:
        lines.append("  · 有 %d 段超过 %d 字：拆成动作/对白/环境三段，避免说明文堆积。" % (
            p["over_300"], VERY_LONG_PARAGRAPH))
    if res["dialogue_ratio"] < 0.15 and res["form"] == "short":
        lines.append("  · 对白偏少：短篇可用对话承担冲突，但别让对话解释设定。")
    if not (cliches or templates or dups or openings):
        lines.append("  · 指标干净。剩下的交给审校与朗读：读出声，删掉读不顺的字。")
    return "\n".join(lines)


def digest(res: Dict[str, Any], max_items: int = 6) -> str:
    """给审校/修订提示词用的紧凑摘要（≤10 行）。"""
    if not res.get("chapters"):
        return ""
    s, p = res["sentences"], res["paragraphs"]
    lines = ["体检分 %d/100（%s）｜%s 字｜对白 %.0f%%" % (
        res["score"], res["grade"], format(res["total_words"], ","),
        res["dialogue_ratio"] * 100)]
    lines.append("- 句长均 %.1f 字，≥%d 字长句 %d 处（%.1f%%），最长 %d 字" % (
        s["avg"], LONG_SENTENCE, s["long_count"], s["long_ratio"] * 100, s["max"]))
    lines.append("- 段长均 %.1f 字，≥%d 字长段 %d 段" % (
        p["avg"], VERY_LONG_PARAGRAPH, p["over_300"]))
    if res["cliche_hits"]:
        samples = "、".join(h["phrase"] for h in res["cliche_hits"][:max_items])
        lines.append("- 陈词滥调 %d 处：%s" % (len(res["cliche_hits"]), samples))
    if res["template_hits"]:
        labels: Dict[str, int] = {}
        for h in res["template_hits"]:
            labels[h["label"]] = labels.get(h["label"], 0) + 1
        lines.append("- AI 腔 %d 处：%s" % (
            len(res["template_hits"]),
            "、".join("%s×%d" % (k, v) for k, v in sorted(labels.items(), key=lambda x: -x[1])[:4])))
    if res["tic_words"]:
        lines.append("- 高频虚词：" + "、".join(
            "%s×%d" % (t["word"], t["count"]) for t in res["tic_words"][:5]))
    if res["dup_sentences"] or res["dup_openings"]:
        lines.append("- 重复：整句 %d 组、段首 %d 组" % (
            len(res["dup_sentences"]), len(res["dup_openings"])))
    end_flags = res.get("end_marker_flags") or []
    if end_flags:
        lines.append("- 收尾异常 %d 章（多重完结标记或完结后续写），优先删除后一套结尾"
                     % len(end_flags))
    sim_pairs = res.get("similar_chapters") or []
    if sim_pairs:
        lines.append("- 跨章高度相似 %d 对：%s"
                     % (len(sim_pairs), "、".join("第%d/%d章" % (p["a"], p["b"])
                                                 for p in sim_pairs[:4])))
    if res["top_ngrams"]:
        lines.append("- 高频四字串：" + "、".join(
            "%s×%d" % (g["phrase"], g["count"]) for g in res["top_ngrams"][:5]))
    return "\n".join(lines)
