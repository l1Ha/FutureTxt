"""流水线各阶段：提示词构建、产物读写、执行逻辑。

阶段顺序：concept → world → characters → outline → draft → review → revise → assemble
"""

import json
import os
import re

import kb
import llm

# ---------------------------------------------------------------- 基础工具

CHAPTER_RE = re.compile(r"^##\s*第\s*(\d+)\s*章[^\n]*$", re.M)


def read(path, default=""):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return default


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip() + "\n")


def clip(text, cap):
    """超长截断：保留头 60% + 尾 40%（尾部通常是「硬性设定规则」）。"""
    text = text or ""
    if len(text) <= cap:
        return text
    head = int(cap * 0.6)
    tail = cap - head
    return text[:head] + "\n…（中间略）…\n" + text[-tail:]


def word_count(text):
    return len(re.sub(r"\s+", "", text or ""))


def chapter_no(path):
    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else 0


class Project:
    """一个小说项目的目录与状态。"""

    def __init__(self, root, name):
        self.root = root
        self.name = name
        self.dir = os.path.join(root, "projects", name)
        self.cfg_path = os.path.join(self.dir, "project.json")
        self.state_path = os.path.join(self.dir, "state.json")

    # -- 配置 --------------------------------------------------------
    def exists(self):
        return os.path.exists(self.cfg_path)

    def config(self):
        return json.loads(read(self.cfg_path, "{}"))

    def save_config(self, cfg):
        write(self.cfg_path, json.dumps(cfg, ensure_ascii=False, indent=2))

    # -- 状态 --------------------------------------------------------
    def state(self):
        return json.loads(read(self.state_path, "{}"))

    def save_state(self, st):
        write(self.state_path, json.dumps(st, ensure_ascii=False, indent=2))

    def mark(self, stage, status):
        st = self.state()
        st.setdefault("stages", {})[stage] = status
        self.save_state(st)

    def summary(self, n):
        return self.state().get("summaries", {}).get(str(n), "")

    def add_summary(self, n, text):
        st = self.state()
        st.setdefault("summaries", {})[str(n)] = text
        self.save_state(st)

    # -- 产物路径 ----------------------------------------------------
    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def f_concept(self):
        return self.path("00-创作概念.md")

    def f_world(self):
        return self.path("01-世界观.md")

    def f_characters(self):
        return self.path("02-角色.md")

    def f_outline(self):
        return self.path("03-大纲.md")

    def chapters_dir(self):
        return self.path("chapters")

    def reviews_dir(self):
        return self.path("reviews")

    def chapter_file(self, n):
        return os.path.join(self.chapters_dir(), "chapter_%03d.md" % n)

    def review_file(self, n):
        return os.path.join(self.reviews_dir(), "chapter_%03d_审校.md" % n)

    def list_chapters(self):
        d = self.chapters_dir()
        if not os.path.isdir(d):
            return []
        files = [os.path.join(d, x) for x in os.listdir(d) if x.endswith(".md")]
        return sorted(files, key=chapter_no)

    def chapters_range(self, only=None):
        """only 形如 '3'、'1-5'、'1,4,7-9'；返回存在的章节号列表。"""
        total = int(self.config().get("target_chapters", 0))
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
    "你是一位成熟的中文科幻小说作家，兼有编辑素养。写作原则：\n"
    "1) 以场景和行动推进，忌大段说明文；世界观信息通过冲突与细节自然滴灌。\n"
    "2) 人物动机清晰，对话有个人语言指纹；术语只在必要时出现并自然解释。\n"
    "3) 严格遵守用户提供的「硬性设定」，不得擅自发明与设定矛盾的科技或历史。\n"
    "4) 输出为纯 Markdown 正文，不要任何解释、前言或免责声明。"
)

SYSTEM_EDITOR = (
    "你是一位严苛的科幻小说责任编辑，熟悉科学常识与叙事工艺。"
    "审校时只指出具体、可执行的问题，引用原文位置；不写客套话。"
)


def _project_brief(cfg):
    keys = cfg.get("keywords") or []
    return "\n".join(
        [
            "书名（暂定）：%s" % cfg.get("title", "未定"),
            "题材关键词：%s" % ("、".join(keys) if keys else "（未提供）"),
            "故事前提（premise）：%s" % (cfg.get("premise") or "（未提供，请根据关键词自行提出）"),
            "目标体量：%d 章 × 约 %d 字（共约 %d 字）"
            % (cfg.get("target_chapters", 20), cfg.get("words_per_chapter", 3000),
               cfg.get("target_chapters", 20) * cfg.get("words_per_chapter", 3000)),
            "叙事视角：%s" % cfg.get("pov", "第三人称有限"),
            "文风基调：%s" % cfg.get("tone", "克制、具象、冷峻中的温度"),
            "目标读者：%s" % cfg.get("audience", "成人科幻读者"),
            "其他要求：%s" % (cfg.get("extra") or "（无）"),
        ]
    )


# ---------------------------------------------------------------- 各阶段


def stage_concept(proj, cfg, api):
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["concept"])
    user = (
        "请为下面的项目生成「创作概念文档」。\n\n"
        "【项目信息】\n%s\n\n【知识库参考】\n%s\n\n"
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
        "## 暂定书名（3个候选）" % (_project_brief(cfg), knowledge)
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, what="创作概念")
    write(proj.f_concept(), out)
    return "00-创作概念.md"


def stage_world(proj, cfg, api):
    concept = read(proj.f_concept())
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["world"], cap=14000)
    user = (
        "请基于创作概念，写出完整「世界观设定文档」。\n\n"
        "【项目信息】\n%s\n\n【创作概念】\n%s\n\n【知识库参考】\n%s\n\n"
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
        % (_project_brief(cfg), concept, knowledge)
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=6000, what="世界观")
    write(proj.f_world(), out)
    return "01-世界观.md"


def stage_characters(proj, cfg, api):
    concept = read(proj.f_concept())
    world = read(proj.f_world())
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["characters"])
    user = (
        "请基于创作概念与世界观，建立本小说的角色体系。\n\n"
        "【项目信息】\n%s\n\n【创作概念】\n%s\n\n【世界观（可截断）】\n%s\n\n"
        "【知识库参考】\n%s\n\n"
        "按以下结构输出：\n# 角色体系\n"
        "## 关系网（谁与谁：依赖/对立/隐瞒）\n"
        "对每个主要角色（主角、2~4 名配角、反派/对立力量）输出：\n"
        "## 角色：姓名\n"
        "- 身份与处境 / 外貌标志（1个易记特征） / 欲望（表层想要） / 需求（深层成长） / "
        "缺陷 / 秘密 / 人物弧光（起点→终点） / 语言指纹（口头禅、术语密度、句长） / 与主线的关系\n"
        "最后输出：\n"
        "## 群像与背景色（名字-身份对照，供次要人物统一使用）\n"
        "## 角色一致性要点（编号 C1、C2… 至少8条，供审校引用）"
        % (_project_brief(cfg), concept, clip(world, 9000), knowledge)
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=6000, what="角色")
    write(proj.f_characters(), out)
    return "02-角色.md"


def parse_outline(text):
    """把大纲切分为 [(章节号, 标题, 条目正文)]。"""
    matches = list(CHAPTER_RE.finditer(text or ""))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = re.sub(r"^##\s*第\s*\d+\s*章\s*", "", m.group(0)).strip()
        out.append((int(m.group(1)), title, text[m.end():end].strip()))
    return out


def stage_outline(proj, cfg, api):
    concept = read(proj.f_concept())
    world = clip(read(proj.f_world()), 7000)
    chars = clip(read(proj.f_characters()), 5000)
    knowledge = kb.load(proj.root, kb.STAGE_MODULES["outline"])
    n = int(cfg.get("target_chapters", 20))
    per = int(cfg.get("words_per_chapter", 3000))
    user = (
        "请创作全书章节大纲。\n\n"
        "【项目信息】\n%s\n\n【创作概念】\n%s\n\n【世界观要点】\n%s\n\n【角色】\n%s\n\n"
        "【知识库参考】\n%s\n\n"
        "严格输出 %d 章（不得多、不得少），每章约 %d 字。结构要求：开篇即入冲突、"
        "约三分之一处中点反转、每章末留钩子、伏笔在大纲中标注「伏笔:」「回收:」。\n\n"
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
        "…（第2章起同格式，直到第%d章）"
        % (_project_brief(cfg), concept, world, chars, knowledge, n, per, n)
    )
    out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                    {"role": "user", "content": user}], api, max_tokens=8000, what="大纲")
    write(proj.f_outline(), out)
    parsed = parse_outline(out)
    return "03-大纲.md（解析到 %d 章，目标 %d 章）" % (len(parsed), n)


def _outline_block(proj, n):
    parsed = parse_outline(read(proj.f_outline()))
    if not parsed:
        return "（大纲未按格式生成，请依据故事走向自由发挥并保持前后一致）"
    idx = {num: (title, body) for num, title, body in parsed}
    parts = []
    for k in (n - 1, n, n + 1):
        if k in idx:
            label = "第%d章" % k + ("（本章）" if k == n else
                                  ("（上一章）" if k == n - 1 else "（下一章）"))
            parts.append("## %s %s\n%s" % (label, idx[k][0], idx[k][1]))
    if n not in idx:
        parts.append("（注意：本章未在大纲中，章节号 %d，请自行衔接）" % n)
    return "\n\n".join(parts)


def _continuity_block(proj):
    st = proj.state()
    sums = st.get("summaries", {})
    if not sums:
        return "（本书第一章）"
    lines = ["此前各章剧情摘要："]
    for k in sorted(sums, key=lambda x: int(x)):
        lines.append("- 第%s章：%s" % (k, sums[k]))
    return clip("\n".join(lines), 3500)


def stage_draft(proj, cfg, api, only=None, force=False):
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
            # 上一章尾部（承接场景与语气）
            prev_tail = ""
            prev = proj.chapter_file(n - 1)
            if n > 1 and os.path.exists(prev):
                prev_tail = clip(read(prev), 1400)
            title = ""
            for num, t, _b in parsed:
                if num == n:
                    title = t
            user = (
                "请写出第 %d 章正文（章名可用：%s）。\n\n"
                "【项目信息】\n%s\n\n【硬性设定与世界观】\n%s\n\n【角色】\n%s\n\n"
                "【本章与邻章大纲】\n%s\n\n【前情摘要】\n%s\n\n【上一章结尾（衔接用）】\n%s\n\n"
                "【写作知识库】\n%s\n\n"
                "要求：正文以「# 第%d章 %s」开头；长度约 %d 字（±15%%）；"
                "开章尽快进入场景，章末落在钩子上；严格遵守硬性设定编号规则。"
                % (n, title or "自拟", _project_brief(cfg), world, chars,
                   _outline_block(proj, n), _continuity_block(proj), prev_tail, knowledge,
                   n, title or "", per)
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                            {"role": "user", "content": user}], api,
                          max_tokens=max(api["max_tokens"], per * 3), what="第%d章" % n)
            if not out.lstrip().startswith("#"):
                out = "# 第%d章 %s\n\n%s" % (n, title or "", out)
            write(fpath, out)
            # 生成本章摘要，供后续章节衔接（失败不致命，只是少了衔接信息）
            try:
                summary = llm.chat(
                    [{"role": "system", "content": "你是剧情记录员。"},
                     {"role": "user", "content": "用120字以内概括这章发生的关键事件、人物状态变化与悬念，只输出摘要：\n\n" + clip(out, 6000)}],
                    api, temperature=0.3, max_tokens=400, what="第%d章摘要" % n)
                proj.add_summary(n, summary)
            except Exception as e:  # noqa: BLE001
                print("    · 第%d章摘要生成失败（不影响正文）：%s" % (n, str(e)[:60]))
            done.append(n)
            print("    ✓ 第%d章 完成（%d字）" % (n, word_count(out)))
        except Exception as e:  # noqa: BLE001
            failed.append(n)
            print("    ✗ 第%d章失败：%s" % (n, str(e)[:100]))
    msg = "正文完成 %d 章%s" % (
        len(done), ("，跳过已有 %d 章" % len(skipped)) if skipped else "")
    if failed:
        raise RuntimeError(
            "%s；失败 %d 章（第 %s 章）——重跑同一命令将自动补写失败章节"
            % (msg, len(failed), "、".join(str(x) for x in failed)))
    return msg


def stage_review(proj, cfg, api, only=None, force=False):
    checklist = kb.load(proj.root, kb.STAGE_MODULES["review"], cap=10000)
    world = clip(read(proj.f_world()), 7000)
    chars = clip(read(proj.f_characters()), 4000)
    outline = clip(read(proj.f_outline()), 5000)
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
                "【审校清单】\n%s\n\n【世界观硬性设定】\n%s\n\n【角色要点】\n%s\n\n"
                "【大纲中的本章任务】\n%s\n\n【章节正文（约目标 %d 字）】\n%s\n\n"
                "输出格式：\n# 第%d章 审校报告\n"
                "## 总评分（1-10，含扣分理由）\n"
                "## 问题清单\n每条：【严重度 高/中/低】位置（引用原文片段≤30字）→ 问题 → 修改建议\n"
                "## 亮点（最多3条）\n"
                "## 结论（一句话：可直接通过 / 需修改后再审）"
                % (checklist, world, chars, _outline_block(proj, n), per,
                   read(src), n)
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_EDITOR},
                            {"role": "user", "content": user}], api,
                          temperature=0.3, max_tokens=3000, what="第%d章审校" % n)
            write(fpath, out)
            done += 1
            score = re.search(r"(\d+(?:\.\d+)?)\s*/?\s*10", out)
            print("    ✓ 第%d章 审校完成%s" % (n, ("，评分 " + score.group(1)) if score else ""))
        except Exception as e:  # noqa: BLE001
            failed.append(n)
            print("    ✗ 第%d章审校失败：%s" % (n, str(e)[:100]))
    if failed:
        raise RuntimeError("完成 %d 份审校；失败第 %s 章（重跑自动补审）"
                           % (done, "、".join(str(x) for x in failed)))
    return "完成 %d 份审校报告" % done


def stage_revise(proj, cfg, api, only=None, force=False):
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
                print("    - 第%d章 无审校报告，先审校…" % n)
                stage_review(proj, cfg, api, only=str(n))
                review = read(proj.review_file(n))
            idx = review.rfind("## 结论")
            conclusion = review[idx:].split("\n", 1)[1] if idx >= 0 else review
            if not force and "可直接通过" in conclusion and "需修改" not in conclusion:
                print("    - 第%d章 审校结论为通过，跳过（--force 可强制修订）" % n)
                continue
            user = (
                "请根据审校报告重写该章，保留原有剧情与硬性设定，只修正报告指出的问题，"
                "并保持与上下章的衔接。\n\n"
                "【世界观硬性设定（截断）】\n%s\n\n"
                "【原文章节】\n%s\n\n【审校报告】\n%s\n\n"
                "输出完整重写后的章节全文（以「# 第%d章 …」开头），长度约 %d 字（±15%%），"
                "纯 Markdown 正文，无任何解释。"
                % (world, read(src), review, n, per)
            )
            out = llm.chat([{"role": "system", "content": SYSTEM_WRITER},
                            {"role": "user", "content": user}], api,
                          max_tokens=max(api["max_tokens"], per * 3), what="第%d章修订" % n)
            if out:
                write(src + ".bak", read(src))
                write(src, out)
                done += 1
                print("    ✓ 第%d章 已修订（原稿存为 .bak）" % n)
        except Exception as e:  # noqa: BLE001
            failed.append(n)
            print("    ✗ 第%d章修订失败：%s" % (n, str(e)[:100]))
    if failed:
        raise RuntimeError("修订 %d 章；失败第 %s 章（重跑自动补修）"
                           % (done, "、".join(str(x) for x in failed)))
    return "修订 %d 章" % done


def stage_assemble(proj, cfg, api=None, **_kw):
    concept = read(proj.f_concept())
    m = re.search(r"^#.*$|书名.*", concept, re.M)
    files = proj.list_chapters()
    if not files:
        raise RuntimeError("没有章节文件，无法汇编。")
    parts = ["---", "title: %s" % cfg.get("title", proj.name),
             "chapters: %d" % len(files),
             "words: %d" % sum(word_count(read(p)) for p in files),
             "---", ""]
    parts.append("# %s\n" % cfg.get("title", proj.name))
    if concept:
        parts.append("## 简介\n\n%s\n" % clip(concept, 600))
    for p in files:
        parts.append(read(p).strip() + "\n\n")
    out_path = proj.path("manuscript", "%s·初稿.md" % cfg.get("title", proj.name))
    text = "\n".join(parts)
    write(out_path, text)
    total = word_count(text)
    return "汇编完成：%s（%d 章 / %d 字）" % (
        os.path.relpath(out_path, proj.root), len(files), total)


STAGES = ["concept", "world", "characters", "outline", "draft", "review", "revise", "assemble"]

STAGE_LABEL = {
    "concept": "创作概念", "world": "世界观", "characters": "角色体系",
    "outline": "大纲", "draft": "正文初稿", "review": "章节审校",
    "revise": "按审校修订", "assemble": "汇编成书",
}
