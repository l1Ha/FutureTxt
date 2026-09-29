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
    "5) 纯 Markdown 正文输出，严禁任何前言、后记、免责声明或寒暄套话。"
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
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["concept"])
    user = (
        "请为下面的项目生成「创作概念文档」。\n\n"
        f"【项目信息】\n{_project_brief(cfg)}\n\n【知识库参考】\n{knowledge}\n\n"
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
        "## 暂定书名（3个候选）"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, what="创作概念")
    write(proj.f_concept(), str(out))
    proj.track_usage("concept")
    return "00-创作概念.md"


def stage_world(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    concept = read(proj.f_concept())
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["world"], cap=14000)
    user = (
        "请基于创作概念，写出完整「世界观设定文档」。\n\n"
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
        "覆盖科技限制、时间线、人物状态、地理规则，供后续写作与审校引用）"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=6000, what="世界观")
    write(proj.f_world(), str(out))
    proj.track_usage("world")
    return "01-世界观.md"


def stage_characters(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    concept = read(proj.f_concept())
    world = read(proj.f_world())
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["characters"])
    user = (
        "请基于创作概念与世界观，建立本小说的角色体系。\n\n"
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


def stage_outline(proj: Project, cfg: Dict[str, Any], api: Dict[str, Any]) -> str:
    concept = read(proj.f_concept())
    world = clip(read(proj.f_world()), 7000)
    chars = clip(read(proj.f_characters()), 5000)
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["outline"])
    n = int(cfg.get("target_chapters", 20))
    per = int(cfg.get("words_per_chapter", 3000))
    user = (
        "请创作全书章节大纲。\n\n"
        f"【项目信息】\n{_project_brief(cfg)}\n\n【创作概念】\n{concept}\n\n【世界观要点】\n{world}\n\n【角色】\n{chars}\n\n"
        f"【知识库参考】\n{knowledge}\n\n"
        f"严格输出 {n} 章（不得多、不得少），每章约 {per} 字。\n"
        "【长篇节奏与三幕式指引】：\n"
        f"- 1~{max(1, int(n * 0.25))}章（第一幕）：开篇即入冲突与建置，以不可逆事件打破日常\n"
        f"- {int(n * 0.25) + 1}~{int(n * 0.5)}章（第二幕上）：危机升级与探索，盟友聚散\n"
        f"- 第{int(n * 0.5)}章（全书中点）：重大认知反转与假象破灭，赌注倍增\n"
        f"- {int(n * 0.5) + 1}~{int(n * 0.75)}章（第二幕下）：对立力量反扑，至暗时刻与代价\n"
        f"- {int(n * 0.75) + 1}~{n}章（第三幕）：总决战，伏笔闭环回收，新常态诞生\n\n"
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
        f"…（第2章起同格式，直到第{n}章）"
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=8000, what="大纲")
    write(proj.f_outline(), str(out))
    proj.track_usage("outline")
    parsed = parse_outline(str(out))
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
    total = int(cfg.get("target_chapters", len(parsed) or 20))
    per = int(cfg.get("words_per_chapter", 3000))
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["draft"], cap=11000)
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

            user = (
                f"请写出第 {n} 章正文（章名可用：{title or '自拟'}）。\n\n"
                f"【项目信息】\n{_project_brief(cfg)}\n\n【硬性设定与世界观】\n{world}\n\n【角色】\n{chars}\n\n"
                f"【本章与邻章大纲】\n{_outline_block(proj, n)}\n\n【前情摘要】\n{_continuity_block(proj)}\n\n"
                f"【上一章结尾（衔接用）】\n{prev_tail}\n\n"
                f"【通用写作知识库】\n{knowledge}{dyn_block}\n\n"
                f"要求：正文以「# 第{n}章 {title or ''}」开头；长度约 {per} 字（±15%）；"
                "开章尽快进入场景，章末落在钩子上；严格遵守硬性设定编号规则。"
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                            {"role": "user", "content": user}], api,
                          max_tokens=max(int(api["max_tokens"]), per * 3), what=f"第{n}章")
            out_str = str(out)
            if not out_str.lstrip().startswith("#"):
                out_str = f"# 第{n}章 {title or ''}\n\n{out_str}"
            write(fpath, out_str)
            proj.track_usage("draft")

            # 生成本章摘要，供后续章节衔接
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
            print(f"    ✓ 第{n}章 完成（{word_count(out_str)}字）")
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
    checklist = kb.load(proj.root, kb.STAGE_MODULES["review"], cap=10000)
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
            user = (
                "请审校下面这一章。\n\n"
                f"【审校清单】\n{checklist}\n\n【世界观硬性设定】\n{world}\n\n【角色要点】\n{chars}\n\n"
                f"【大纲中的本章任务】\n{_outline_block(proj, n)}\n\n【章节正文（约目标 {per} 字）】\n{read(src)}\n\n"
                f"输出格式：\n# 第{n}章 审校报告\n"
                "## 总评分（1-10，含扣分理由）\n"
                "## 问题清单\n每条：【严重度 高/中/低】位置（引用原文片段≤30字）→ 问题 → 修改建议\n"
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
            user = (
                "请根据审校报告重写该章，保留原有剧情与硬性设定，只修正报告指出的问题，"
                "并保持与上下章的衔接。\n\n"
                f"【世界观硬性设定（截断）】\n{world}\n\n"
                f"【原文章节】\n{read(src)}\n\n【审校报告】\n{review}\n\n"
                f"输出完整重写后的章节全文（以「# 第{n}章 …」开头），长度约 {per} 字（±15%），"
                "纯 Markdown 正文，无任何解释。"
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                            {"role": "user", "content": user}], api,
                          max_tokens=max(int(api["max_tokens"]), per * 3), what=f"第{n}章修订")
            out_str = str(out)
            if out_str:
                write(src + ".bak", read(src))
                write(src, out_str)
                proj.track_usage("revise")
                done += 1
                print(f"    ✓ 第{n}章 已修订（原稿存为 .bak）")
        except Exception as e:
            failed.append(n)
            print(f"    ✗ 第{n}章修订失败：{str(e)[:100]}")

    if failed:
        raise RuntimeError(f"修订 {done} 章；失败第 {'、'.join(str(x) for x in failed)} 章（重跑自动补修）")
    return f"修订 {done} 章"


def stage_assemble(proj: Project, cfg: Dict[str, Any], api: Optional[Dict[str, Any]] = None, **_kw: Any) -> str:
    concept = read(proj.f_concept())
    files = proj.list_chapters()
    if not files:
        raise RuntimeError("没有章节文件，无法汇编。")
    title = cfg.get("title", proj.name)
    parts = ["---", f"title: {title}",
             f"chapters: {len(files)}",
             f"words: {sum(word_count(read(p)) for p in files)}",
             "---", ""]
    parts.append(f"# {title}\n")
    if concept:
        parts.append(f"## 简介\n\n{clip(concept, 600)}\n")
    for p in files:
        parts.append(read(p).strip() + "\n\n")

    out_path = proj.path("manuscript", f"{title}·初稿.md")
    text = "\n".join(parts)
    write(out_path, text)
    total = word_count(text)

    # 自动同时生成出版级电子书格式 (EPUB, HTML, TXT)
    export_msg = ""
    try:
        dist_res = export.export_all(proj, formats=["epub", "html", "txt"])
        export_msg = f"；已同步导出 EPUB/HTML/TXT 至 dist/"
    except Exception as e:
        export_msg = f"（电子书导出提示: {e}）"

    return f"汇编完成：{os.path.relpath(out_path, proj.root)}（{len(files)} 章 / {total:,} 字{export_msg}）"


STAGES = ["concept", "world", "characters", "outline", "draft", "review", "revise", "assemble"]

STAGE_LABEL = {
    "concept": "创作概念", "world": "世界观", "characters": "角色体系",
    "outline": "大纲", "draft": "正文初稿", "review": "章节审校",
    "revise": "按审校修订", "assemble": "汇编成书",
}
