"""流水线各阶段：提示词构建、产物读写、执行逻辑。

阶段顺序：concept → world → characters → outline → draft → review → revise → assemble
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import export
import kb
import llm

# ---------------------------------------------------------------- 基础工具

CHAPTER_RE = re.compile(r"^##\s*第\s*(\d+)\s*章[^\n]*$", re.M)


def read(path: str, default: str = "") -> str:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return default


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip() + "\n")


def clip(text: str, cap: int) -> str:
    """超长截断：保留头 60% + 尾 40%（尾部通常是「硬性设定规则」）。"""
    text = text or ""
    if len(text) <= cap:
        return text
    head = int(cap * 0.6)
    tail = cap - head
    return text[:head] + "\n…（中间略）…\n" + text[-tail:]


def word_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def chapter_no(path: str) -> int:
    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------- 质量红线（规则固化）

# 章尾字数尾注（元信息，禁止出现在文稿中）
META_NOTE_RE = re.compile(r"[ \t]*（(?:全[章节]|全文)约\s*\d{2,6}\s*字）[ \t]*")

# 中文语境夹生外语词 → 中文
STRAY_WORDS = {
    "nods": "点头", "hésitation": "犹豫", "earlier": "先前",
    "heaviness": "沉重感", "deja vu": "既视感",
}
STRAY_RE = re.compile(
    r"(?<=[一-鿿])\s+(%s)\s*(?=[一-鿿，。、；：？！）」])"
    % "|".join(re.escape(w) for w in STRAY_WORDS)
)

# 高频错别字表
TYPOS = {
    "眉头一皖": "眉头一皱",
    "不容置疑的决顾": "不容置疑的决绝",
    "曾参余热": "曾参与余热",
    "自我毁启动": "自毁启动",
}


def clean(text):
    """文稿卫生清洗（幂等）：剔除元信息尾注、修复夹生外语词与高频错别字。"""
    if not text:
        return text
    text = META_NOTE_RE.sub("", text)
    text = STRAY_RE.sub(lambda m: STRAY_WORDS[m.group(1)], text)
    for bad, good in TYPOS.items():
        text = text.replace(bad, good)
    return re.sub(r"\n{3,}", "\n\n", text)


def work_form(cfg: Dict[str, Any]) -> str:
    """作品形态：'short'＝短篇单篇 / 'novel'＝长篇多章（默认）。"""
    return "short" if str(cfg.get("work_type", "novel")).lower() == "short" else "novel"


def _kb(proj: Project, cfg: Dict[str, Any], stage: str, cap: Optional[int] = None) -> str:
    """按作品形态注入知识模块（短篇追加 10-短篇写作）。"""
    mods = kb.stage_modules(stage, work_form(cfg))
    return kb.load(proj.root, mods, cap=cap) if cap else kb.load(proj.root, mods)


def quality_rules(per, form: str = "novel"):
    """注入写作/修订提示词的质量红线（源自作品品质复盘）。"""
    if form == "short":
        return (
            "1) **单一效果**：全篇只服务一个统一印象（一个主角、一个处境、一个转折、一个余味）；"
            "删掉后不损害该印象的段落一律不写。\n"
            "2) **开场三十字内落地**：第一句须有具体的人、地点与压力；前 200 字出现具体麻烦；"
            "禁止天气开场、抒情铺垫、世界观导览。\n"
            "3) **只有一个转折**，且必须来自主角自己的选择（不得靠巧合/外力）；转折前须埋一个可复看的伏笔。\n"
            "4) **结尾不解释**：落在动作、物件或一句话上，禁止旁白总结主题、禁止排比抒情拔高、禁止二次反转。\n"
            "5) **语言经济**：删副词与形容词堆叠；细节须可触可量（价格/时长/温度/距离）；"
            "对话不承担解释任务。\n"
            "6) **未来为镜·映射当下**：只映射一件现实结构，靠人物付出的**具体代价**显形。\n"
            "7) 长度：全篇实际汉字数须达到约 %d 字的 85%% 以上（不足将被闸门自动补足）。" % per
        )
    return (
        "1) 跨章唯一：同一场景桥段（发现/备份/对峙/揭秘/牺牲）全书只展开一次；"
        "结尾句与章末钩子不得与任何已完成章节雷同；同一句台词不重复（口头禅每章至多2次）。\n"
        "2) 数字自洽：同一指标全文一个值；引用硬性设定编号时数值必须与规则表一致；换算必须可验算。\n"
        "3) 文本卫生：禁止夹生英文/法文词（nods、earlier、heaviness、hésitation、deja vu，一律用中文）；"
        "禁止元信息（「全文约3020字」「章节在这里戛然而止」之类）；警惕错别字（皱/决绝/参与/自毁）。\n"
        "4) 视角不越界：一章一个视角，与项目设定一致。\n"
        "5) 设定引用点到为止：规则编号每章至多3处且须伴随情节作用；单段技术说明不超过200字。\n"
        "6) 未来为镜·映射当下：每项设定必须映射一个可辨认的**现实**社会结构"
        "（劳动/债务与信贷/数据与隐私/验证与信誉/气候与配额/迁移与身份/平台权力/医疗与身体…），"
        "且须在情节中以**人物付出的具体代价**显形；不得只做科技奇观或悬空设定。\n"
        "7) 长度：实际汉字数须达到约 %d 字的 85%% 以上（不足将被闸门自动扩写一次）。" % per
    )


def _enforce_length(api, n, title, per, text):
    """字数闸门：低于目标 85% 时自动补足。返回 (text, note)。

    两段式策略：
    ① 整体扩写——部分模型有效；
    ② 续写拼接——沿章尾往下写新内容再拼接。对「整体不肯变长、
       但会顺接续写」的模型（如 nemotron-3-ultra）第二步才是有效手段。
    """
    need = int(per * 0.85)
    best = text
    wc0 = word_count(META_NOTE_RE.sub("", text))
    if wc0 >= need:
        return text, ""

    # ① 整体扩写
    try:
        out = llm.chat(
            [{"role": "system", "content": SYSTEM_WRITER},
             {"role": "user", "content":
              "把下面这章扩写到约 %d 字（当前仅约 %d 字）。保持章首行、剧情事件与硬性设定完全不变，"
              "通过动作细节、环境感知、对话与心理推进自然扩长；不得新增重大事件，不得添加任何解释性"
              "或字数统计类元信息。直接输出扩写后的完整章节。\n\n%s" % (per, wc0, text)}],
            api, max_tokens=max(int(api["max_tokens"]), per * 3),
            what="第%d章扩写" % n)
        if out:
            if not out.lstrip().startswith("#"):
                out = "# 第%d章 %s\n\n%s" % (n, title or "", out)
            out = clean(out)
            if word_count(out) > word_count(best):
                best = out
    except Exception:  # noqa: BLE001
        pass

    # ② 续写拼接兜底（最多两轮；单轮索取封顶，防止模型单次暴涨 3~5 倍）
    for _ in range(2):
        wc = word_count(META_NOTE_RE.sub("", best))
        if wc >= need:
            break
        add = min(max(int(need - wc) + 200, 500), 1200)
        try:
            cont = llm.chat(
                [{"role": "system", "content": SYSTEM_WRITER},
                 {"role": "user", "content":
                  "这是本章的结尾片段：\n\n%s\n\n"
                  "请**接着往下写**约 %d 字的续写内容（同一场景、紧接的下一步动作与对话），"
                  "不要重复或概括上述已有情节，不要加章标题，不要任何解释性文字，"
                  "直接输出续写正文。" % (best[-1000:], add)}],
                api, max_tokens=max(int(api["max_tokens"]), add * 3),
                what="第%d章续写" % n)
        except Exception as e:  # noqa: BLE001
            return best, "；⚠字数闸门：%d字不足且续写失败（%s）" % (wc, str(e)[:50])
        cont = clean(str(cont or ""))
        cont = re.sub(r"^#{1,3}\s*第\s*\d+\s*章[^\n]*\n+", "", cont).strip()
        if word_count(cont) < 150:
            break
        best = best.rstrip() + "\n\n" + cont

    wc1 = word_count(META_NOTE_RE.sub("", best))

    # ③ 明显超长（>1.5 倍目标）时压缩一次，吸收单轮续写的暴涨
    if wc1 > int(per * 1.5):
        try:
            squeezed = llm.chat(
                [{"role": "system", "content": SYSTEM_WRITER},
                 {"role": "user", "content":
                  "下面这章约 %d 字，明显超出篇幅要求。请压缩到约 %d 字：保留全部剧情事件、"
                  "人物行动与章末钩子，删除重复的环境铺陈与冗余修饰，不得删掉任何关键情节；"
                  "章首行保持不变，不得添加任何字数统计或元信息。直接输出压缩后的完整章节。\n\n%s"
                  % (wc1, per, best)}],
                api, max_tokens=max(int(api["max_tokens"]), per * 3),
                what="第%d章压缩" % n)
            squeezed = clean(str(squeezed or ""))
            wc2 = word_count(META_NOTE_RE.sub("", squeezed))
            if int(need * 0.9) <= wc2 < wc1:      # 压到接近目标才采纳
                best, wc1 = squeezed, wc2
        except Exception:  # noqa: BLE001
            pass

    # 保底：任何闸门路径都不得丢失章首行（否则会连带英译丢失章标题）
    if best and not META_NOTE_RE.sub("", best).lstrip().startswith("#"):
        best = "# 第%d章 %s\n\n%s" % (n, title or "", best.lstrip())
        wc1 = word_count(META_NOTE_RE.sub("", best))

    if wc1 < need:
        return best, "；⚠字数闸门：%d→%d字仍低于目标85%%，请人工关注" % (wc0, wc1)
    return best, "（字数闸门：%d→%d字）" % (wc0, wc1)


def machine_precheck(files, per):
    """连续性机器预检：跨章重复整句、雷同结尾、字数、卫生残留（确定性结果）。"""
    sent_map, endings, wc_short, hygiene = {}, {}, [], []
    for p in files:
        n = chapter_no(p)
        text = read(p)
        wc = word_count(text)
        if wc < per * 0.85:
            wc_short.append("第%d章 %d字（%d%%）" % (n, wc, round(wc * 100 / max(per, 1))))
        meta = META_NOTE_RE.findall(text)
        stray = STRAY_RE.findall(text)
        typos = [b for b in TYPOS if b in text]
        if meta or stray or typos:
            hygiene.append("第%d章：字数尾注%d、夹生外语%d、错别字%d"
                           % (n, len(meta), len(stray), len(typos)))
        body = re.sub(r"^#.*$", "", text, flags=re.M)
        sents = [s.strip() for s in re.split(r"[。！？!?\n]+", body) if len(s.strip()) >= 14]
        for s in sents:
            sent_map.setdefault(s, []).append(n)
        if sents:
            endings.setdefault(sents[-1], []).append(n)
    dups = [(s, sorted(set(ns))) for s, ns in sent_map.items() if len(set(ns)) > 1]
    dups.sort(key=lambda t: -len(t[0]))
    end_dups = [(s, sorted(set(ns))) for s, ns in endings.items() if len(set(ns)) > 1]
    lines = []
    if wc_short:
        lines.append("- **字数不足 85%%**（%d 章）：%s" % (len(wc_short), "；".join(wc_short)))
    if dups:
        lines.append("- **跨章重复整句**（≥14字，出现在 2 章以上）：共 %d 处，示例：" % len(dups))
        for s, ns in dups[:10]:
            lines.append("  - 「%s…」 ← 第%s章" % (s[:40], "、".join(str(x) for x in ns)))
    if end_dups:
        lines.append("- **雷同结尾句**：%s" % "；".join(
            "「%s…」← 第%s章" % (s[:30], "、".join(str(x) for x in ns)) for s, ns in end_dups[:5]))
    if hygiene:
        lines.append("- **卫生残留**（应由 clean() 处理）：" + "；".join(hygiene))
    if not lines:
        lines.append("- 未发现字数、重复、卫生类问题")
    return "\n".join(lines), len(dups) + len(end_dups) + len(wc_short) + len(hygiene)


class Project:
    """一个小说项目的目录与状态。"""

    def __init__(self, root: str, name: str) -> None:
        self.root = root
        self.name = name
        self.dir = os.path.join(root, "projects", name)
        self.cfg_path = os.path.join(self.dir, "project.json")
        self.state_path = os.path.join(self.dir, "state.json")

    # -- 配置 --------------------------------------------------------
    def exists(self) -> bool:
        return os.path.exists(self.cfg_path)

    def config(self) -> Dict[str, Any]:
        return json.loads(read(self.cfg_path, "{}"))

    def save_config(self, cfg: Dict[str, Any]) -> None:
        write(self.cfg_path, json.dumps(cfg, ensure_ascii=False, indent=2))

    # -- 状态 --------------------------------------------------------
    def state(self) -> Dict[str, Any]:
        return json.loads(read(self.state_path, "{}"))

    def save_state(self, st: Dict[str, Any]) -> None:
        write(self.state_path, json.dumps(st, ensure_ascii=False, indent=2))

    def mark(self, stage: str, status: str) -> None:
        st = self.state()
        st.setdefault("stages", {})[stage] = status
        self.save_state(st)

    def summary(self, n: int) -> str:
        return self.state().get("summaries", {}).get(str(n), "")

    def add_summary(self, n: int, text: str) -> None:
        st = self.state()
        st.setdefault("summaries", {})[str(n)] = text
        self.save_state(st)

    def track_usage(self, stage: str, usage: Optional[Dict[str, int]] = None) -> None:
        """记录各阶段 Token 用量消耗。"""
        u = usage or llm.get_last_usage()
        if not u or not any(u.values()):
            return
        st = self.state()
        tu = st.setdefault("token_usage", {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "by_stage": {},
        })
        p = u.get("prompt_tokens", 0)
        c = u.get("completion_tokens", 0)
        t = u.get("total_tokens", p + c)
        tu["prompt_tokens"] += p
        tu["completion_tokens"] += c
        tu["total_tokens"] += t

        bs = tu["by_stage"].setdefault(stage, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        bs["prompt_tokens"] += p
        bs["completion_tokens"] += c
        bs["total_tokens"] += t
        self.save_state(st)

    def set_score(self, chapter: int, score: float) -> None:
        st = self.state()
        st.setdefault("scores", {})[str(chapter)] = score
        self.save_state(st)

    def dossier(self) -> Dict[str, Any]:
        return self.state().get("dossier", {})

    def update_dossier(self, updates: Dict[str, Any]) -> None:
        st = self.state()
        d = st.setdefault("dossier", {})
        d.update(updates)
        self.save_state(st)

    # -- 产物路径 ----------------------------------------------------
    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)

    def f_concept(self) -> str:
        return self.path("00-创作概念.md")

    def f_world(self) -> str:
        return self.path("01-世界观.md")

    def f_characters(self) -> str:
        return self.path("02-角色.md")

    def f_outline(self) -> str:
        return self.path("03-大纲.md")

    def chapters_dir(self) -> str:
        return self.path("chapters")

    def reviews_dir(self) -> str:
        return self.path("reviews")

    def chapter_file(self, n: int) -> str:
        return os.path.join(self.chapters_dir(), f"chapter_{n:03d}.md")

    def review_file(self, n: int) -> str:
        return os.path.join(self.reviews_dir(), f"chapter_{n:03d}_审校.md")

    def list_chapters(self) -> List[str]:
        d = self.chapters_dir()
        if not os.path.isdir(d):
            return []
        files = [os.path.join(d, x) for x in os.listdir(d) if x.endswith(".md") and not x.endswith(".bak")]
        return sorted(files, key=chapter_no)

    def chapters_range(self, only: Optional[str] = None) -> List[int]:
        """only 形如 '3'、'1-5'、'1,4,7-9'；返回存在的章节号列表。"""
        exist = [chapter_no(p) for p in self.list_chapters()]
        if only:
            picked = set()
            for part in str(only).split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    picked.update(range(int(a), int(b) + 1))
                elif part:
                    picked.add(int(part))
            exist = [n for n in exist if n in picked]
            exist.sort()
        return exist


# ---------------------------------------------------------------- 系统提示

SYSTEM_WRITER = (
    "你是一位荣获雨果奖、星云奖水准的世界级中文科幻小说作家。吸收特德·姜的严谨思想实验推演、"
    "刘慈欣的宏大冷酷宇宙张力与威廉·吉布森的粗粝通感白描。核心文学工艺铁律：\n"
    "1) 坚决破除说明文塑料感：严禁开篇设定讲座；世界观与硬科技必须通过人物身体的生理磨损、感官不适、"
    "生存代价与物理阻力隐形滴灌（Show, Don't Explain）。\n"
    "2) 感官具象与电影质感：开篇第一段必须包含至少两种感官细节（声音、气味、温度、触觉）；"
    "科技道具充满工业磨损与细节真实感。\n"
    "3) 人物动机与存在主义困境：拒绝脸谱化善恶，冲突源于宇宙物理客观法则与人类情感尊严的不可调和；"
    "对话富有个性语言指纹，坚决杜绝悬浮汇报式对话。\n"
    "4) 严格遵守世界观硬性设定编号（W1..Wn）与角色一致性铁律（C1..Cn），逻辑闭环推演至极。\n"
    "5) 纯 Markdown 正文输出，严禁任何前言、后记、免责声明、寒暄套话或字数统计尾注"
    "（如「全文约3020字」）；不得出现 meta 叙述（如「章节在这里戛然而止」）"
    "与中文语境下的夹生外语单词（nods、earlier、heaviness 等，一律用中文）。"
)

SYSTEM_EDITOR = (
    "你是一位顶级科幻出版机构的严苛主编，以菲利普·迪克、特德·姜作品的审校标准审视稿件。"
    "严格扫描：①是否有超过400字的干燥说明文；②科学常识是否违背已知力学/热力学常理；"
    "③角色对话是否悬浮假大空；④章节末尾是否落在具备强烈悬念的钩子上。直接指出具体缺陷并给出修改建议。"
)


def _project_brief(cfg: Dict[str, Any]) -> str:
    keys = cfg.get("keywords") or []
    target_ch = int(cfg.get("target_chapters", 20))
    words_per = int(cfg.get("words_per_chapter", 3000))
    return "\n".join(
        [
            f"书名（暂定）：{cfg.get('title', '未定')}",
            f"题材关键词：{'、'.join(keys) if keys else '（未提供）'}",
            f"故事前提（premise）：{cfg.get('premise') or '（未提供，请根据关键词自行提出）'}",
            f"目标体量：{target_ch} 章 × 约 {words_per} 字（共约 {target_ch * words_per:,} 字）",
            f"叙事视角：{cfg.get('pov', '第三人称有限')}",
            f"文风基调：{cfg.get('tone', '克制、具象、冷峻中的温度')}",
            f"目标读者：{cfg.get('audience', '成人科幻读者')}",
            f"其他要求：{cfg.get('extra') or '（无）'}",
        ]
    )


# ---------------------------------------------------------------- 各阶段


def stage_concept(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    knowledge = _kb(proj, cfg, "concept")
    form_note = (
        "【形态：短篇单篇】全篇只有一个主角、一个处境、一个转折、一个余味；"
        "三层冲突请收敛为「一处代价」；现实映射表至少 3 行即可——聚焦一件事，把它压到底。\n\n"
        if work_form(cfg) == "short" else "")
    user = (
        "请为下面的项目生成「创作概念文档」。\n\n"
        f"【项目信息】\n{_project_brief(cfg)}\n\n{form_note}【知识库参考】\n{knowledge}\n\n"
        "按以下结构输出（Markdown）：\n"
        "# 创作概念\n"
        "## 一句话卖点（logline，80字内）\n"
        "## 故事前提展开（300字内）\n"
        "## 核心冲突（至少三层：个人/社会/观念）\n"
        "## 主题与承载的思想实验\n"
        "## 子类型与基调\n"
        "## 主角简述（身份+欲望+缺陷，100字内）\n"
        "## 结局走向\n"
        "## 创新点（说明与常见套路的区别）\n"
        "## 现实映射表（未来为镜，至少 5 行）\n"
        "表格四列：| 核心设定 | 对应的当代社会结构 | 推到极端的哪一点 | 情节中的显形方式 |\n"
        "要求：每行都要能回答「它对应今天的什么」；显形方式必须是**人物付出的具体代价**，"
        "不得写成说明文或科技名词堆砌。\n"
        "## 暂定书名（3个候选）"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, what="创作概念")
    write(proj.f_concept(), str(out))
    proj.track_usage("concept")
    return "00-创作概念.md"


def stage_world(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    concept = read(proj.f_concept())
    knowledge = _kb(proj, cfg, "world", cap=14000)
    form_note = (
        "【形态：短篇单篇】无需五层全覆盖，只写与故事直接相关的那几层；"
        "硬性设定 W1… 至少 5 条即可（不必 12 条），每条都要能在本篇里被用到；"
        "现实映射表至少 3 行。\n\n" if work_form(cfg) == "short" else "")
    user = (
        "请基于创作概念，写出完整「世界观设定文档」。\n\n"
        f"{form_note}"
        f"【项目信息】\n{_project_brief(cfg)}\n\n【创作概念】\n{concept}\n\n【知识库参考】\n{knowledge}\n\n"
        "按以下结构输出：\n"
        "# 世界观设定\n"
        "## 一、一句话概括\n"
        "## 二、科技设定（核心技术清单：原理、水平、代价与限制）\n"
        "## 三、时间线与历史（关键年代编年，表格）\n"
        "## 四、地理与空间（星球/城市/飞船/殖民地，尺度感明确）\n"
        "## 五、社会制度与政治经济（权力结构、阶层、经济运作）\n"
        "## 六、文化、宗教与日常（语言、习俗、衣食住行细节）\n"
        "## 七、硬性设定（本项目必须遵守的铁律，编号 W1、W2… 至少12条，"
        "覆盖科技限制、时间线、人物状态、地理规则，供后续写作与审校引用）\n"
        "## 八、现实映射表（未来为镜）\n"
        "表格四列：| 设定/编号 | 对应的当代社会结构 | 推到极端的哪一点 | 情节中的显形方式 |\n"
        "要求：至少 8 行、覆盖主要 W 规则；显形方式必须落在**人物付出的具体代价**上"
        "（一顿饭的价格、一次挂号的资格、一句不能说的话），不得是说明文或名词堆砌。"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=6000, what="世界观")
    write(proj.f_world(), str(out))
    proj.track_usage("world")
    return "01-世界观.md"


def stage_characters(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    concept = read(proj.f_concept())
    world = read(proj.f_world())
    knowledge = _kb(proj, cfg, "characters")
    form_note = (
        "【形态：短篇单篇】角色只保留出场所需的 2~3 人（主角 + 1~2 名配角/对立面），"
        "每人必须有明确的语言指纹与一个可复看的标志物；一致性要点 C1… 至少 5 条即可。\n\n"
        if work_form(cfg) == "short" else "")
    user = (
        "请基于创作概念与世界观，建立本小说的角色体系。\n\n"
        f"{form_note}"
        f"【项目信息】\n{_project_brief(cfg)}\n\n【创作概念】\n{concept}\n\n【世界观（可截断）】\n{clip(world, 9000)}\n\n"
        f"【知识库参考】\n{knowledge}\n\n"
        "按以下结构输出：\n# 角色体系\n"
        "## 关系网（谁与谁：依赖/对立/隐瞒）\n"
        "对每个主要角色（主角、2~4 名配角、反派/对立力量）输出：\n"
        "## 角色：姓名\n"
        "- 身份与处境 / 外貌标志（1个易记特征） / 欲望（表层想要） / 需求（深层成长） / "
        "缺陷 / 秘密 / 人物弧光（起点→终点） / 语言指纹（口头禅、术语密度、句长） / 与主线的关系\n"
        "最后输出：\n"
        "## 群像与背景色（名字-身份对照，供次要人物统一使用）\n"
        "## 角色一致性要点（编号 C1、C2… 至少8条，供审校引用）"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=6000, what="角色")
    write(proj.f_characters(), str(out))
    proj.track_usage("characters")
    return "02-角色.md"


def parse_outline(text: str) -> List[Tuple[int, str, str]]:
    """把大纲切分为 [(章节号, 标题, 条目正文)]。"""
    matches = list(CHAPTER_RE.finditer(text or ""))
    out: List[Tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = re.sub(r"^##\s*第\s*\d+\s*章\s*", "", m.group(0)).strip()
        out.append((int(m.group(1)), title, text[m.end():end].strip()))
    return out


def outline_count_block(cfg: Dict[str, Any]) -> Tuple[bool, str, str, str]:
    """大纲提示词中的章数规则块。

    返回 (auto, 章数规则, 三幕节奏指引, 结尾格式行)。
    - `chapters_mode: fixed`（默认）：严格输出 target_chapters 章；
    - `chapters_mode: auto`：**章数由情节决定**（建议 min_chapters~max_chapters 章），
      大纲成为章数的唯一权威（正文/成书阶段均以解析大纲的章数为准）。
    """
    if work_form(cfg) == "short":
        per = int(cfg.get("words_per_chapter", 6000))
        count_rule = (
            "**本作为短篇单篇**：只输出**一个**章节块作为全篇结构方案，全篇约 %d 字；"
            "不得拆分章节，不设多幕分章节点。\n" % per)
        act_rule = (
            "【短篇结构要点（都写进那一个章块里）】：\n"
            "- 单一效果：一句话能说出「读完后读者应该感到 ___」\n"
            "- 开场：三十字内落地（具体的人/地点/压力），前 200 字出现具体麻烦\n"
            "- 中段：**只有一个转折**，必须来自主角自身的选择；转折前埋一个可复看的伏笔\n"
            "- 结尾：落在动作/物件/台词上，不解释主题、不二次反转\n")
        return True, count_rule, act_rule, "（只输出第1章一个块，不要更多章节）"
    n = int(cfg.get("target_chapters", 20))
    per = int(cfg.get("words_per_chapter", 3000))
    auto = str(cfg.get("chapters_mode", "fixed")).lower() == "auto"
    lo = max(2, int(cfg.get("min_chapters", 5)))
    hi = max(lo, int(cfg.get("max_chapters", 12)))
    if auto:
        count_rule = (
            "**章数由情节决定**：请根据故事推进的实际需要自行确定章节总数"
            "（建议 %d~%d 章，每章约 %d 字）；不得为凑数拆章，也不得为压缩硬并——"
            "每一章都必须承载一次独立的事件推进与章末钩子。\n" % (lo, hi, per))
        act_rule = (
            "【三幕式节奏（按实际章数自行换算比例）】：\n"
            "- 第一幕（约前 1/4）：开篇即入冲突与建置，以不可逆事件打破日常\n"
            "- 第二幕上（约 1/4~1/2）：危机升级与探索，盟友聚散\n"
            "- 中点（全书正中的那一章）：重大认知反转与假象破灭，赌注倍增\n"
            "- 第二幕下（约 1/2~3/4）：对立力量反扑，至暗时刻与代价\n"
            "- 第三幕（最后 1/4）：总决战，伏笔闭环回收，新常态诞生\n")
        return auto, count_rule, act_rule, "…（第2章起同格式，直到最后一章）"
    count_rule = "严格输出 %d 章（不得多、不得少），每章约 %d 字。\n" % (n, per)
    act_rule = (
        "【长篇节奏与三幕式指引】：\n"
        "- 1~%d章（第一幕）：开篇即入冲突与建置，以不可逆事件打破日常\n"
        "- %d~%d章（第二幕上）：危机升级与探索，盟友聚散\n"
        "- 第%d章（全书中点）：重大认知反转与假象破灭，赌注倍增\n"
        "- %d~%d章（第二幕下）：对立力量反扑，至暗时刻与代价\n"
        "- %d~%d章（第三幕）：总决战，伏笔闭环回收，新常态诞生\n"
        % (max(1, int(n * 0.25)), int(n * 0.25) + 1, int(n * 0.5), int(n * 0.5),
           int(n * 0.5) + 1, int(n * 0.75), int(n * 0.75) + 1, n))
    return auto, count_rule, act_rule, "…（第2章起同格式，直到第%d章）" % n


def stage_outline(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    concept = read(proj.f_concept())
    world = clip(read(proj.f_world()), 7000)
    chars = clip(read(proj.f_characters()), 5000)
    knowledge = _kb(proj, cfg, "outline")
    n = int(cfg.get("target_chapters", 20))
    per = int(cfg.get("words_per_chapter", 3000))
    auto, count_rule, act_rule, last_line = outline_count_block(cfg)
    user = (
        "请创作全书章节大纲。\n\n"
        f"【项目信息】\n{_project_brief(cfg)}\n\n【创作概念】\n{concept}\n\n【世界观要点】\n{world}\n\n【角色】\n{chars}\n\n"
        f"【知识库参考】\n{knowledge}\n\n"
        f"{count_rule}"
        f"{act_rule}\n"
        "每章末必须留钩子，伏笔在大纲中标注「伏笔:」「回收:」。\n\n"
        "格式（严格遵守，便于机器解析）：\n"
        "# 全书大纲\n"
        "## 故事线概览（200字内）\n"
        "## 第1章 章节标题\n"
        "- 场景（地点与时间）：\n"
        "- 本章目标：\n"
        "- 核心冲突：\n"
        "- 转折/结果：\n"
        "- 信息与世界观揭示：\n"
        "- 伏笔/回收：\n"
        "- 章末钩子：\n"
        f"{last_line}"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=8000, what="大纲")
    write(proj.f_outline(), str(out))
    proj.track_usage("outline")
    parsed = parse_outline(str(out))
    if auto:
        return f"03-大纲.md（**章数由情节决定：{len(parsed)} 章**，每章约 {per} 字）"
    return f"03-大纲.md（解析到 {len(parsed)} 章，目标 {n} 章）"


def _outline_block(proj: Project, n: int) -> str:
    parsed = parse_outline(read(proj.f_outline()))
    if not parsed:
        return "（大纲未按格式生成，请依据故事走向自由发挥并保持前后一致）"
    idx = {num: (title, body) for num, title, body in parsed}
    parts = []
    for k in (n - 1, n, n + 1):
        if k in idx:
            label = f"第{k}章" + ("（本章）" if k == n else
                                  ("（上一章）" if k == n - 1 else "（下一章）"))
            parts.append(f"## {label} {idx[k][0]}\n{idx[k][1]}")
    if n not in idx:
        parts.append(f"（注意：本章未在大纲中，章节号 {n}，请自行衔接）")
    return "\n\n".join(parts)


def _continuity_block(proj: Project) -> str:
    st = proj.state()
    sums = st.get("summaries", {})
    dossier = st.get("dossier", {})
    if not sums and not dossier:
        return "（本书第一章）"
    lines = []
    if dossier:
        if "timeline" in dossier:
            lines.append(f"【当前故事时间/坐标】{dossier['timeline']}")
        if "active_clues" in dossier and dossier["active_clues"]:
            lines.append("【待兑现/正在推进的伏笔悬念】")
            for c in dossier["active_clues"][-4:]:
                lines.append(f"- {c}")
    if sums:
        lines.append("此前各章剧情摘要：")
        for k in sorted(sums, key=lambda x: int(x)):
            lines.append(f"- 第{k}章：{sums[k]}")
    return clip("\n".join(lines), 3800)


def stage_draft(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any], only: Optional[str] = None, force: bool = False) -> str:
    """逐章生成正文。"""
    parsed = parse_outline(read(proj.f_outline()))
    # 章数以大纲为唯一权威（auto 模式下大纲自行决定章数）
    total = len(parsed) or int(cfg.get("target_chapters", 20))
    per = int(cfg.get("words_per_chapter", 3000))
    form = work_form(cfg)
    knowledge = _kb(proj, cfg, "draft", cap=11000)
    world = clip(read(proj.f_world()), 9000)
    chars = clip(read(proj.f_characters()), 5000)

    wanted = []
    for part in str(only or "").split(","):
        part = part.strip()
        if "-" in part and part:
            a, b = part.split("-", 1)
            wanted.extend(range(int(a), int(b) + 1))
        elif part:
            wanted.append(int(part))
    targets = wanted if wanted else list(range(1, total + 1))

    done, skipped, failed = [], [], []
    for n in targets:
        fpath = proj.chapter_file(n)
        if os.path.exists(fpath) and not force:
            skipped.append(n)
            continue
        try:
            prev_tail = ""
            prev = proj.chapter_file(n - 1)
            if n > 1 and os.path.exists(prev):
                prev_tail = clip(read(prev), 1400)
            title = ""
            for num, t, _b in parsed:
                if num == n:
                    title = t

            # 动态智能检索本章关键词关联的科学/设定小节（局部轻量 RAG）
            dyn_query = f"{title} {_outline_block(proj, n)[:300]}"
            dyn_snippets = kb.retrieve_snippets(proj.root, dyn_query, cap=2000)
            dyn_block = f"\n\n【本章针对性科学与方法论参考】\n{dyn_snippets}" if dyn_snippets else ""

            if form == "short":
                user = (
                    f"请写出本短篇的**完整正文**（篇名可用：{title or '自拟'}）。\n\n"
                    f"【项目信息】\n{_project_brief(cfg)}\n\n【硬性设定与世界观】\n{world}\n\n【角色】\n{chars}\n\n"
                    f"【本篇结构方案】\n{_outline_block(proj, n)}\n\n"
                    f"【通用写作知识库】\n{knowledge}{dyn_block}\n\n"
                    f"【短篇质量红线（违反即返工）】\n{quality_rules(per, 'short')}\n\n"
                    f"要求：正文以「# 第{n}章 {title or ''}」开头；**全篇约 {per} 字（±15%）**；"
                    "严格遵守短篇工艺——开场三十字内落地（具体的人/地点/压力）、前 200 字出现具体麻烦、"
                    "**全篇只有一个转折且必须来自主角自己的选择**、转折前埋一个可复看的伏笔、"
                    "结尾落在动作/物件/台词上（不解释主题、不二次反转）；"
                    "未来为镜：把设定映射到一个现实结构，并靠**一处具体代价**显形；"
                    "不得出现任何章节外的元信息。"
                )
            else:
                user = (
                    f"请写出第 {n} 章正文（章名可用：{title or '自拟'}）。\n\n"
                    f"【项目信息】\n{_project_brief(cfg)}\n\n【硬性设定与世界观】\n{world}\n\n【角色】\n{chars}\n\n"
                    f"【本章与邻章大纲】\n{_outline_block(proj, n)}\n\n【前情摘要】\n{_continuity_block(proj)}\n\n"
                    f"【上一章结尾（衔接用）】\n{prev_tail}\n\n"
                    f"【通用写作知识库】\n{knowledge}{dyn_block}\n\n"
                    f"【质量红线（违反即返工）】\n{quality_rules(per)}\n\n"
                    f"要求：正文以「# 第{n}章 {title or ''}」开头；长度约 {per} 字（±15%）；"
                    "开章尽快进入场景，章末落在钩子上；严格遵守硬性设定编号规则；"
                    "本章内容不得复用前情摘要或上一章结尾中已发生过的场景。"
                )
            out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                            {"role": "user", "content": user}], api,
                          max_tokens=max(int(api["max_tokens"]), per * 3), what=f"第{n}章")
            out_str = str(out)
            if not out_str.lstrip().startswith("#"):
                out_str = f"# 第{n}章 {title or ''}\n\n{out_str}"
            out_str = clean(out_str)
            out_str, gate_note = _enforce_length(api, n, title, per, out_str)
            write(fpath, out_str)
            proj.track_usage("draft")

            # 生成本章摘要，供后续章节衔接（短篇单篇无需摘要）
            if form != "short":
                try:
                    summary = llm.chat(
                        [{"role": "system", "content": "你是剧情记录员。"},
                         {"role": "user", "content": "用120字以内概括这章发生的关键事件、人物状态变化与悬念，只输出摘要：\n\n" + clip(out_str, 6000)}],
                        api, temperature=0.3, max_tokens=400, what=f"第{n}章摘要")
                    proj.add_summary(n, str(summary).strip())
                    proj.track_usage("draft")
                except Exception as e:
                    print(f"    · 第{n}章摘要生成失败（不影响正文）：{str(e)[:60]}")

            done.append(n)
            print(f"    ✓ 第{n}章 完成（{word_count(out_str)}字）{gate_note}")
        except Exception as e:
            failed.append(n)
            print(f"    ✗ 第{n}章失败：{str(e)[:100]}")

    msg = f"正文完成 {len(done)} 章" + (f"，跳过已有 {len(skipped)} 章" if skipped else "")
    if failed:
        raise RuntimeError(
            f"{msg}；失败 {len(failed)} 章（第 {'、'.join(str(x) for x in failed)} 章）——重跑同一命令将自动补写失败章节"
        )
    return msg


def stage_review(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any], only: Optional[str] = None, force: bool = False) -> str:
    checklist = _kb(proj, cfg, "review", cap=10000)
    world = clip(read(proj.f_world()), 7000)
    chars = clip(read(proj.f_characters()), 4000)
    per = int(cfg.get("words_per_chapter", 3000))
    targets = proj.chapters_range(only)
    if not targets:
        targets = list(range(1, int(cfg.get("target_chapters", 20)) + 1))
    done, failed = 0, []

    for n in targets:
        src = proj.chapter_file(n)
        if not os.path.exists(src):
            continue
        fpath = proj.review_file(n)
        if os.path.exists(fpath) and not force:
            continue
        try:
            neigh = []
            if n > 1 and proj.summary(n - 1):
                neigh.append("- 第%d章：%s" % (n - 1, proj.summary(n - 1)))
            if proj.summary(n + 1):
                neigh.append("- 第%d章：%s" % (n + 1, proj.summary(n + 1)))
            neigh_block = ("\n【相邻章节摘要（供跨章检查）】\n%s\n" % "\n".join(neigh)) if neigh else ""
            user = (
                "请审校下面这一章。\n\n"
                f"【审校清单】\n{checklist}\n\n【质量红线】\n{quality_rules(per)}\n\n"
                f"【世界观硬性设定】\n{world}\n\n【角色要点】\n{chars}\n\n"
                f"【大纲中的本章任务】\n{_outline_block(proj, n)}\n{neigh_block}"
                f"【章节正文（约目标 {per} 字）】\n{read(src)}\n\n"
                f"输出格式：\n# 第{n}章 审校报告\n"
                "## 总评分（1-10，含扣分理由）\n"
                "## 问题清单\n每条：【严重度 高/中/低】位置（引用原文片段≤30字）→ 问题 → 修改建议\n"
                "必须含跨章检查结论：与相邻章的重复场景/重复台词/雷同结尾、数值矛盾；"
                "若确无此类问题，显式写一条「跨章检查：无问题」。\n"
                "## 亮点（最多3条）\n"
                "## 结论（一句话：可直接通过 / 需修改后再审）"
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_EDITOR},
                            {"role": "user", "content": user}], api,
                          temperature=0.3, max_tokens=3000, what=f"第{n}章审校")
            write(fpath, str(out))
            proj.track_usage("review")
            done += 1
            score_m = re.search(r"(\d+(?:\.\d+)?)\s*/?\s*10", str(out))
            if score_m:
                proj.set_score(n, float(score_m.group(1)))
            print(f"    ✓ 第{n}章 审校完成" + (f"，评分 {score_m.group(1)}" if score_m else ""))
        except Exception as e:
            failed.append(n)
            print(f"    ✗ 第{n}章审校失败：{str(e)[:100]}")

    if failed:
        raise RuntimeError(f"完成 {done} 份审校；失败第 {'、'.join(str(x) for x in failed)} 章（重跑自动补审）")
    return f"完成 {done} 份审校报告"


def stage_revise(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any], only: Optional[str] = None, force: bool = False) -> str:
    per = int(cfg.get("words_per_chapter", 3000))
    world = clip(read(proj.f_world()), 7000)
    targets = proj.chapters_range(only)
    if not targets:
        targets = list(range(1, int(cfg.get("target_chapters", 20)) + 1))
    done, failed = 0, []

    for n in targets:
        src = proj.chapter_file(n)
        if not os.path.exists(src):
            continue
        try:
            review = read(proj.review_file(n))
            if not review:
                print(f"    - 第{n}章 无审校报告，先审校…")
                stage_review(proj, cfg, api, only=str(n))
                review = read(proj.review_file(n))
            idx = review.rfind("## 结论")
            conclusion = review[idx:].split("\n", 1)[1] if idx >= 0 else review
            if not force and "可直接通过" in conclusion and "需修改" not in conclusion:
                print(f"    - 第{n}章 审校结论为通过，跳过（--force 可强制修订）")
                continue
            src_text = clean(read(src))
            cont_report = read(proj.path("reviews", "全书连续性报告.md"))
            next_sum = "\n【下一章摘要（不得提前消耗其事件）】\n第%d章：%s\n" % (
                n + 1, proj.summary(n + 1)) if proj.summary(n + 1) else ""
            cont_block = ("\n【全书连续性报告（涉及本章的问题优先修）】\n%s\n"
                          % clip(cont_report, 3000)) if cont_report else ""
            user = (
                "请根据审校报告重写该章，保留原有剧情与硬性设定，只修正报告指出的问题。\n\n"
                f"【质量红线（违反即返工）】\n{quality_rules(per)}\n\n"
                f"【大纲中的本章任务与邻章】\n{_outline_block(proj, n)}\n\n【前情摘要】\n{_continuity_block(proj)}\n{next_sum}"
                f"【世界观硬性设定（截断）】\n{world}\n{cont_block}"
                f"【原文章节】\n{src_text}\n\n【审校报告】\n{review}\n\n"
                "特别注意：重写不得引入其他章节已出现过的场景、对白、结尾句；"
                "不得复用前情摘要中已发生过的桥段；只修复报告所列问题。\n"
                f"输出完整重写后的章节全文（以「# 第{n}章 …」开头），长度约 {per} 字（±15%），"
                "纯 Markdown 正文，无任何解释。"
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                            {"role": "user", "content": user}], api,
                          max_tokens=max(int(api["max_tokens"]), per * 3), what=f"第{n}章修订")
            out_str = str(out)
            if out_str:
                mtitle = re.search(r"^#\s*(.+)$", src_text, re.M)
                if not out_str.lstrip().startswith("#"):
                    out_str = ("# %s\n\n%s" % (mtitle.group(1).strip() if mtitle else "第%d章" % n,
                                              out_str)) if mtitle else f"# 第{n}章\n\n{out_str}"
                out_str = clean(out_str)
                out_str, gate_note = _enforce_length(api, n, "", per, out_str)
                write(src + ".bak", read(src))
                write(src, out_str)
                proj.track_usage("revise")
                done += 1
                print(f"    ✓ 第{n}章 已修订（原稿存为 .bak）{gate_note}")
        except Exception as e:
            failed.append(n)
            print(f"    ✗ 第{n}章修订失败：{str(e)[:100]}")

    if failed:
        raise RuntimeError(f"修订 {done} 章；失败第 {'、'.join(str(x) for x in failed)} 章（重跑自动补修）")
    return f"修订 {done} 章"


def stage_continuity(proj, cfg, api, only=None, force=False):
    """全书连续性审校：机器预检（确定性） + LLM 跨章复核，报告落盘 reviews/。"""
    files = proj.list_chapters()
    if not files:
        raise RuntimeError("没有章节文件，无法做连续性审校。")
    report_path = proj.path("reviews", "全书连续性报告.md")
    if os.path.exists(report_path) and not force:
        return "已存在：%s（--force 可重做）" % os.path.relpath(report_path, proj.root)
    per = int(cfg.get("words_per_chapter", 3000))
    machine_md, issue_count = machine_precheck(files, per)

    sums = proj.state().get("summaries", {})
    parts = []
    for p in files:
        n = chapter_no(p)
        body = re.sub(r"^#.*$", "", read(p), flags=re.M).strip()
        parts.append("### 第%d章\n- 摘要：%s\n- 开头：%s…\n- 结尾：…%s" % (
            n, sums.get(str(n), "（无摘要，据首尾判断）"),
            re.sub(r"\s+", " ", body[:180]), re.sub(r"\s+", " ", body[-180:])))
    evidence = clip("\n\n".join(parts), 16000)
    knowledge = _kb(proj, cfg, "continuity", cap=6000)
    user = (
        "请做全书连续性审校——只看跨章问题（单章内部问题已由章节审校负责）。\n\n"
        "【全书大纲（截断）】\n%s\n\n【质量红线与审校清单】\n%s\n\n"
        "【各章证据（摘要与首尾节选）】\n%s\n\n"
        "必查：1) 跨章重复场景/桥段/台词/结尾句；2) 数值与时间线矛盾（含与硬性设定冲突）；"
        "3) 章末钩子雷同；4) 视角越界；5) 人物状态前后矛盾。\n\n"
        "输出格式：\n# 跨章复核\n## 问题清单\n每条：【严重度 高/中/低】涉及章节 → 问题 → 修改建议\n"
        "## 结论（一句话：全书通过 / 需修改后再审）"
        % (clip(read(proj.f_outline()), 5000), knowledge, evidence)
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_EDITOR},
                    {"role": "user", "content": user}], api,
                   temperature=0.3, max_tokens=4000, what="全书连续性")
    report = ("# 全书连续性报告\n\n"
              "阶段：continuity（机器预检 + LLM 跨章复核）　章节数：%d\n\n"
              "## 机器预检（脚本，结果确定）\n%s\n\n%s"
              % (len(files), machine_md, out))
    write(report_path, report)
    return "连续性报告：%s（机器预检发现 %d 项问题）" % (
        os.path.relpath(report_path, proj.root), issue_count)


def stage_assemble(proj: Project, cfg: Dict[str, Any], api: Optional[Dict[str, Any]] = None, **_kw: Any) -> str:
    concept = clean(read(proj.f_concept()))
    concept = re.sub(r"^#[^\n]*\n", "", concept).strip()  # 去掉概念稿标题，避免混入成书
    files = proj.list_chapters()
    if not files:
        raise RuntimeError("没有章节文件，无法汇编。")
    title = cfg.get("title", proj.name)
    form = work_form(cfg)
    chapter_words = sum(word_count(clean(read(p))) for p in files)
    parts = ["---", f"title: {title}",
             f"form: {form}",
             f"chapters: {len(files)}",
             f"words: {chapter_words}",
             "---", ""]
    parts.append(f"# {title}\n")
    if concept:
        parts.append(f"## 简介\n\n{clip(concept, 600)}\n")
    for p in files:
        body = clean(read(p)).strip()
        if form == "short":  # 短篇单篇：去掉「# 第1章 …」行，正文即全篇
            body = re.sub(r"^#\s*第\s*\d+\s*章[^\n]*\n+", "", body).strip()
        parts.append(body + "\n\n")

    out_path = proj.path("manuscript", f"{title}·初稿.md")
    text = "\n".join(parts)
    write(out_path, text)
    total = chapter_words

    # 自动同时生成出版级电子书格式 (EPUB, HTML, TXT)
    export_msg = ""
    try:
        export.export_all(proj, formats=["epub", "html", "txt"])
        export_msg = f"；已同步导出 EPUB/HTML/TXT 至 dist/"
    except Exception as e:
        export_msg = f"（电子书导出提示: {e}）"

    # 全书字数 85% 闸门告警
    target = len(files) * int(cfg.get("words_per_chapter", 3000))
    warn = ""
    if target and chapter_words < target * 0.85:
        warn = f"；⚠ 全书字数为目标({target:,})的 {round(chapter_words * 100 / target)}%，低于 85% 闸门，建议补写"

    scale = "单篇" if form == "short" else f"{len(files)} 章"
    return f"汇编完成：{os.path.relpath(out_path, proj.root)}（{scale} / {total:,} 字{export_msg}）{warn}"


STAGES = ["concept", "world", "characters", "outline",
          "draft", "review", "revise", "continuity", "assemble"]

STAGE_LABEL = {
    "concept": "创作概念", "world": "世界观", "characters": "角色体系",
    "outline": "大纲", "draft": "正文初稿", "review": "章节审校",
    "revise": "按审校修订", "continuity": "全书连续性", "assemble": "汇编成书",
}
