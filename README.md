# FutureTxt —— 科幻小说知识库 + 自动化创作流水线

面向中文长篇科幻小说的专业创作系统：**36 篇独家方法论知识库** 动态注入 **9 阶段智能创作流水线**，
从一句题材关键词一路产出「概念 → 世界观 → 角色 → 大纲 → 逐章正文 → 逐章审校 → 修订 → 全书连续性审校 → 汇编成书 → 出版级导出（EPUB / HTML / TXT）」。

**纯 Python 标准库实现（Python 3.8+），零第三方依赖，跨平台（Windows / macOS / Linux）通用。**

---

## 核心亮点与系统能力

- 🧠 **36 篇科幻方法论知识库**：涵盖概论、硬核世界观自上而下因果推演、7大科学顾问（物理/天文/生物/AI/工程/医学/社会学）、角色语言指纹、悬念伏笔闭环与 72 条审稿清单。
- 🚦 **文稿质量红线（`09-质量规则`）**：源自《意识纪元》《地球2200》两部全稿品质复盘的固化规则——跨章唯一、数字自洽、字数闸门、文本卫生、视角与引用密度，自动注入写作/审校/修订/连续性四个阶段，并由机器检查强制兜底。
- ⚖️ **多模块动态预算均衡（防知识饥饿）**：多知识模块注入时自动均衡字符配额，彻底解决前期世界观文档吃光额度、导致科学顾问被饿死的问题；超长文档智能保头（概念原理）保尾（速查清单与铁律）。
- 🔍 **轻量动态 RAG 与相关度重排**：正文起草时根据每章剧情大纲，自动动态检索匹配关联科学顾问小节并定向注入；知识库全文检索支持相关度打分排序。
- 📊 **小说数据全景与文学工艺指标 (`stats`)**：一键生成全书规模统计、默读与演播时长换算、字数极差/波动差标准差、章节篇幅字符柱状图、对白占比分析（警惕说明文过载）以及核心角色聚光灯（出场/提及频次）。
- 🛡️ **设定与伏笔闭环审计引擎 (`audit`)**：全自动索引世界观硬规则（W1..Wn）与角色一致性规则（C1..Cn），扫描大纲未兑现伏笔、幽灵回收以及章节内超长单段说明文（Infodump）。
- 📚 **出版级多格式导出 (`export`)**：
  - **EPUB 3.0**：符合 IDPF 国际标准的电子书包（包含未压缩 mimetype、元数据、NCX/Nav 目录、扉页与精美中文排版 CSS，可直推 Apple Books、微信读书、Kindle 等）；
  - **HTML 沉浸式离线阅读器**：独立单文件离线网页，支持亮暗色主题切换、字号无级缩放、侧边栏目录跳转与阅读进度；
  - **规范排版 TXT**：全角段首缩进与标准卷标分隔。
- 🩺 **系统自检诊断门诊 (`doctor`)**：环境体检、知识库完整性校验、API 连通性测试与网络延迟分析。
- 🛡️ **生产级 LLM 通信守护**：内置 SSE 流式保活（抗 WinError 10054 网络掐断）、指数退避重试、思考模型（GLM/DeepSeek-R1/Kimi）Token 烧光智能加倍保护、Token 用量与成本分阶段统计。

---

## 目录结构

```
FutureTxt/
├── knowledge/                 # 科幻写作知识库（36 篇，完整版）
│   ├── 01-概论/               # 定义与历史、子类型全景、思想实验
│   ├── 02-世界观/             # 构建方法、科技可信度、社会、时间线、地理、文化日常
│   ├── 03-科学顾问/           # 物理、天文、生物、AI、工程、医学、社会学
│   ├── 04-角色/               # 角色构建、反派与对立力量、对话与语言指纹
│   ├── 05-情节结构/           # 整体结构与节奏、章节与钩子、悬念与信息释放
│   ├── 06-文风与叙事/         # 视角、描写沉浸感、解释性写作、高级修辞与感官白描
│   ├── 07-素材与创意/         # 灵感方法、常见套路清单、反套路创新
│   ├── 08-参考/               # 经典作品分析、术语表、审稿清单、大师叙事工艺、母题图谱
│   └── 09-质量规则/           # 文稿质量红线（源自全稿品质复盘，自动注入写作/审校/修订）
├── pipeline/                  # 自动化流水线
│   ├── run.py                 # 统一命令行入口（支持彩色终端与多子命令）
│   ├── stages.py              # 9 阶段提示词工程、状态记忆池、质量红线/字数闸门/终稿清洗/机器预检
│   ├── llm.py                 # 生产级 OpenAI 兼容客户端（流式保活、用量追踪、截断扩充）
│   ├── kb.py                  # 知识库均衡预算加载、智能分词检索与局部动态 RAG
│   ├── export.py              # 纯标准库 EPUB 3.0 / 单文件 HTML 阅读器 / 规范 TXT 导出
│   ├── analytics.py           # 小说全景字数统计、对白占比、篇幅分布柱状图、角色聚光灯
│   ├── audit.py               # 设定圣经 W/C 规则与大纲伏笔闭环一致性审计
│   ├── bundle_kb.py           # 知识库打包（Web 端离线知识包）
│   └── doctor.py              # 全系统环境、知识库完整性与端点连通性自检
├── tests/                     # 自动化单元测试套件（零外部依赖，一键运行）
├── web/                       # 免服务器 PWA 创作端（EPUB 打包、离线缓存、GitHub Pages）
├── benchmark_models.py        # 候选模型横测工具（延时 + 中文创作质量）
├── projects/<项目名>/         # 每本小说一个独立工作区
│   ├── project.json           # 书名、题材关键词、章节数、字数、叙事视角等配置
│   ├── state.json             # 阶段状态、逐章剧情摘要与 Token 用量追踪（断点续跑）
│   ├── 00-创作概念.md          # Logline、三层冲突、思想实验、书名候选
│   ├── 01-世界观.md            # 五层世界推演 + 硬性设定铁律清单 W1..Wn
│   ├── 02-角色.md              # 角色弧光、语言指纹 + 一致性要点 C1..Cn
│   ├── 03-大纲.md              # 三幕式结构大纲（场景/目标/冲突/转折/伏笔/钩子）
│   ├── chapters/chapter_*.md  # 逐章正文（自动保存 .bak 备份）
│   ├── reviews/chapter_*_审校.md # 依据 72 条清单的逐章严苛审校报告
│   ├── reviews/全书连续性报告.md # 跨章重复/矛盾机器预检 + LLM 复核
│   ├── manuscript/《书名》·初稿.md # 全书汇编稿
│   ├── dist/                  # 中文出版交付物（.epub / .html / .txt）
│   ├── chapters_en/           # 英文译稿（translate 支线产出）
│   ├── glossary_en.md         # 中英术语对照表（人名/机构/货币/阶级统一）
│   ├── blurb_en.md            # 英文版简介
│   └── dist_en/               # 英文出版交付物（export --lang en）
├── config.json                # LLM API 配置（不入库密钥，见下）
└── README.md
```

---

## 快速开始

### 1. 系统自检与环境体检
```bash
python pipeline/run.py doctor
```

### 2. 配置 API 端点
支持任何 OpenAI 兼容接口（如 DeepSeek、月之暗面、通义千问、OpenAI、NVIDIA NIM、vLLM、Ollama 等）：
```bash
python pipeline/run.py config --api-key sk-xxx \
    --base-url https://api.openai.com/v1 --model gpt-4o-mini
```
*或设置环境变量：`SCIWRITE_API_KEY`、`SCIWRITE_BASE_URL`、`SCIWRITE_MODEL`。*

### 3. 创建小说项目
```bash
python pipeline/run.py init 赛博侦探 \
    --keywords "赛博朋克,侦探,记忆交易,社会分层" \
    --premise "在记忆可以买卖的近未来城市，一名侦探发现所有离奇命案都指向自己被抹除的过去" \
    --chapters 20 --words 3000 --pov "第三人称有限" --tone "冷峻、克制中有温度"
```

**章数模式**（`--chapters-mode`）：

- `fixed`（默认）：严格写死 `--chapters` 章；
- `auto`：**章数由情节决定**——大纲阶段自行定章数（建议 `--min-chapters`~`--max-chapters`，默认 5–12），
  且**大纲成为章数的唯一权威**：正文、审校、成书阶段均以解析大纲得到的实际章数为准
  （`target_chapters` 在 auto 模式下只作规划参考）。适合"故事该多长就多长"的写法。

```bash
python pipeline/run.py init 原件纪元 --chapters-mode auto --min-chapters 5 --max-chapters 12 \
    --asset-prefix YuanJianJiYuan
```

### 4. 一键跑通全流程
```bash
python pipeline/run.py run 赛博侦探
```

### 5. 查看进度与 Token 消耗
```bash
python pipeline/run.py status 赛博侦探
```

---

## 流水线 9 阶段

| 阶段 | 产物 | 知识库注入重点 | 说明 |
|---|---|---|---|
| `concept` | 00-创作概念.md | 概论、素材与创意 | 确立 Logline、三层冲突、思想实验、结局与创新点 |
| `world` | 01-世界观.md | 世界观、科学顾问全册 | 科技/时间线/地理/社会/文化 + **硬性设定 W1…Wn** 铁律清单 |
| `characters` | 02-角色.md | 角色构建、文化日常 | 欲望/需求/缺陷/语言指纹 + **角色一致性 C1…Cn** |
| `outline` | 03-大纲.md | 情节结构、反套路策略 | 精确 N 章三幕式展开：目标/冲突/转折/信息揭示/伏笔/钩子 |
| `draft` | chapters/*.md | **09-质量规则**、文风叙事、动态科学片段 | 逐章创作：前情摘要 + 邻章大纲 + 上章结尾衔接 + 局部 RAG + **质量红线**；**字数闸门**（<85% 自动扩写一次）；写入前自动 `clean()` |
| `review` | reviews/*_审校.md | **09-质量规则**、72条审稿清单、科学顾问 | 对照硬规则打分（1-10）；注入相邻章摘要，**必查跨章重复/数值矛盾/钩子雷同** |
| `revise` | 覆盖正文（.bak备份） | **09-质量规则**、文风叙事、情节结构 | 注入大纲+前情+下一章摘要+连续性报告，**禁止引入他章已有场景**；结论「可直接通过」智能跳过；同样过字数闸门 |
| `continuity` | reviews/全书连续性报告.md | **09-质量规则**、审稿清单 | **机器预检**（跨章重复整句/雷同结尾/字数/卫生残留，确定性）+ **LLM 跨章复核** |
| `assemble` | manuscript/初稿.md + dist/* | 全书合并 | `clean()` 清洗 + 全书字数 85% 闸门告警，并自动生成 EPUB、HTML 与 TXT 出版交付件 |

### 质量红线（两部全稿品质复盘 → 固化规则）

完整规则见 `knowledge/09-质量规则/01-文稿质量红线.md`，三条最有价值的经验：

1. **跨章唯一**：场景桥段/结尾句/名句全书只出现一次——第4、5章整段复刻的教训，
   现由「前情摘要+连续性审校+机器重复句预检」三层拦截；
2. **字数只认脚本统计**：模型自报「全文约3020字」虚报可达 28%，一律以 `word_count()` 为准，
   低于目标 85% 触发闸门补足。闸门为**两段式**：① 整体扩写；② 仍不足则**沿章尾续写拼接**——
   实测推理型模型（nemotron-3-ultra-550b）会让章节稳定停在 ~1700 字，且明确要求「扩写到 2300 字」
   也只给 1717 字，但**顺着结尾续写**能自然产出千余字新内容；故续写是兜底主力。
   注意 `max_tokens` 需覆盖「思考 token + 正文」，推理模型下建议 ≥16k；
3. **任何项目不得跳过审校链**：`review → revise → continuity` 缺一不可
   （前车之鉴：《意识纪元》20 章零审校，机器预检一次就查出 16 处跨章重复）。

---

## 常用进阶命令

### 1. 小说文学工艺指标分析 (`stats`)
```bash
python pipeline/run.py stats 赛博侦探
```
输出包含：
- 全书总字数、段落数、常人默读预估时长、有声演播时长；
- 章节篇幅均值、极差、标准差波动；
- 终端 ASCII/Unicode 字数节奏柱状图；
- 对白字数占比（监测是否陷入纯解说）；
- 核心角色出场/提及频次聚光灯。

### 2. 设定圣经与伏笔闭环审计 (`audit`)
```bash
python pipeline/run.py audit 赛博侦探
```
自动校验世界观 W 规则、角色 C 规则覆盖度，统计大纲伏笔与回收链路，并标记正文单段字数超标（Infodump 风险）。

### 3. 多格式电子书导出 (`export`)
```bash
python pipeline/run.py export 赛博侦探 --format all     # 导出全部 (epub, html, txt)
python pipeline/run.py export 赛博侦探 --format epub    # 仅导出 EPUB 电子书
python pipeline/run.py export 赛博侦探 --format html    # 仅导出离线交互式阅读网页
```
导出产物自动保存在 `projects/<项目名>/dist/` 目录下。

> **锚点剥离（审校版 / 出版版分离）**：导出默认自动剥离（W5）（C3、C5）（日常细节2）
> （起床与光照）等三族锚点（W/C 设定规则、日常细节清单、条目标题标签），
> `dist/` 即出版净稿；章节与 `manuscript/` 成书保留锚点，供审校与 `audit` 溯源；
> `--keep-anchors` 可导出带标记版。

### 3.5 双语发行：中文 + 英文双版本 (`translate`)
```bash
python pipeline/run.py translate 赛博侦探            # 中文 → 英文（先生成术语表，再逐章翻译）
python pipeline/run.py translate 赛博侦探 --only 3   # 仅翻译第 3 章（--force 可重译）
python pipeline/run.py export 赛博侦探 --lang en     # 导出英文版 → dist_en/（标题带 English Edition）
```
主水线只产中文；`translate` 支线把已完成章节译为**出版级英文**：先从世界观/角色文档
一次性生成「中文 = English」术语表（保证人名、机构、货币、阶级称谓全书统一），
再逐章翻译——反引号代码段（哈希/编号）整体保护不译，章首行规范为 `# Chapter N: Title`，
并产出英文简介 `blurb_en.md`。`export --lang en` 读 `chapters_en/`、产物落 `dist_en/`，
EPUB/HTML/TXT 的界面文案（作者/目录/上一章/字数…）与语言标记全部切换为英文。

### 3.6 一键发行到 GitHub Releases (`release`)
```bash
python pipeline/run.py release 赛博侦探 --dry-run            # 本地打包预览（不触碰 GitHub）
python pipeline/run.py release 赛博侦探 --prefix CyberNoir   # 打包 + 创建发行（版本号自动递增）
python pipeline/run.py release 赛博侦探 --tag novels-v1.5    # 指定标签（已存在则覆盖更新）
```
一条命令完成「打包 → 生成说明 → 发布 → 校验」：

- **附件自动 ASCII 化**：GitHub Release 资产名只接受 ASCII，中文名会被静默剥离
  （实测 `意识纪元.epub` → `default.epub`、`地球2200.epub` → `2200.epub`）。
  故附件按 `asset_prefix`（拼音）命名：`<prefix>.{epub,html,txt}`（中文版）与
  `<prefix>-EN.{epub,html,txt}`（英文版，存在 `dist_en/` 时自动纳入）。
  前缀取自 `--prefix` 或 `project.json` 的 `asset_prefix`（`init --asset-prefix` 可预置），
  两者皆无时给出明确指引而非发布出 `default.epub`。
- **说明自动生成**：中文简介取净稿 TXT 的【作品简介】，英文简介取 `blurb_en.md`，
  附「附件-作品对照表」与出版约定（锚点剥离、审校版位置等）。
- **版本号自动递增**：从既有发行标签推断，`novels-v1.0 → novels-v1.1 → …`。
- **可重入**：标签已存在时改为「覆盖上传附件 + 更新说明」，不会重复建发行；
  发布后回读资产并校验名称全为 ASCII（防止 `default.epub` 静默事故）。
- 打包产物落在 `projects/<项目名>/release_build/`（已 gitignore）。

### 4. 灵活分步与区间控制
```bash
python pipeline/run.py run 赛博侦探 --stages draft --only 1-5     # 仅写第 1~5 章
python pipeline/run.py run 赛博侦探 --stages review --only 3       # 仅审第 3 章
python pipeline/run.py run 赛博侦探 --stages revise --force        # 强制修订
python pipeline/run.py run 赛博侦探 --stages continuity            # 全书跨章连续性审校（机器预检+LLM）
python pipeline/run.py run 赛博侦探 --stages outline --force       # 重做大纲
python pipeline/run.py run 赛博侦探 --stages assemble              # 重新汇编与导出
```

### 5. 知识库智能检索
```bash
python pipeline/run.py kb 戴森球       # 检索知识库，按相关度权重展示高匹配段落
python pipeline/run.py kb 曲率引擎
python pipeline/run.py kb              # 列出全部 36 篇方法论文档
```

### 断点续跑

所有阶段均检查产物是否存在：中断后重跑同一命令会**自动跳过已完成部分**（正文按章节文件存在判断，
世界观等按文件存在判断，`--force` 可重做）。每章生成后会记录 120 字剧情摘要到 `state.json`，
供后续章节衔接，全书任意位置续写都保留上下文。

---

## 知识库如何被使用

`pipeline/kb.py` 按阶段映射注入相关模块（多模块动态预算均衡，单阶段上限 1.4~2 万字符，
超长文件保头保尾，确保文末的「硬性设定」「要点速查」不被截掉）：

- `concept` ← 01-概论、07-素材与创意
- `world` ← 02-世界观全册、03-科学顾问全册
- `characters` ← 04-角色、文化日常篇
- `outline` ← 05-情节结构、07-素材与创意
- `draft` ← **09-质量规则**、06-文风与叙事、05-情节结构、对话篇、科技可信度、术语表
- `review` ← **09-质量规则**、08-参考/03-审稿自查清单（72 条）、03-科学顾问
- `revise` ← **09-质量规则**、06-文风与叙事、05-情节结构
- `continuity` ← **09-质量规则**、08-参考/03-审稿自查清单

也可以脱离流水线，直接把这些文档当作写作参考，或复制其中的提示词手工使用。

---

## 配置说明

`config.json`（由 `run.py config` 写入）：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `base_url` | `https://api.openai.com/v1` | 任意 OpenAI 兼容接口根地址 |
| `api_key` | 空 | 也可用环境变量 `SCIWRITE_API_KEY` |
| `model` | `gpt-4o-mini` | 见下方「模型实测建议」 |
| `temperature` | 0.8 | 创作温度 |
| `max_tokens` | 4096 | 单次输出上限（正文会自动按每章字数放大） |
| `timeout` / `retries` | 600 / 5 | 秒 / 网络错误·429·5xx 自动重试次数 |
| `extra_params` | `{}` | 端点扩展参数，如 `{"reasoning_effort": "minimal"}` |

`projects/<名>/project.json`（由 `run.py init` 生成）：`title`、`keywords`、`premise`、
`target_chapters`、`words_per_chapter`、`pov`、`tone`、`audience`、`extra`。
建好后可直接改这个文件再 `--force` 重跑对应阶段。

---

## 运行自动化测试

本项目坚持零第三方依赖原则，所有测试均使用 Python 标准库 `unittest`：

```bash
python -m unittest discover tests
```
*包含 LLM 客户端容错、知识库均衡加载、大纲切分、EPUB 电子书封装、小说数据统计与一致性审计、*
*三族锚点剥离（W/C、日常细节、标题标签 + 病句 fixup + export_all 端到端）、*
*双语导出链路（英文章节选取 / dist_en / 英文界面文案）、一键发行打包（ASCII 附件命名 / 版本递增 /
说明生成 / dry-run）、CLI 参数契约回归等 49 项全功能单元测试。*

---

## 模型实测建议

- 推荐使用非推理大参数模型（如 `nvidia/nemotron-3-super-120b-a12b`、`gpt-4o`、`deepseek-chat`）以获得最平稳的中文正文输出速度。
- 若选用推理模型（如 DeepSeek-R1、GLM-Zero、Kimi），系统已内置 `reasoning_content` 截断防护，遇到思考耗尽时将自动加倍扩展 `max_tokens`（上限 32000）并安全重试。
- **换模型前先横测**：`python benchmark_models.py`（延迟 + 中文创作质量双维度）。
- ⚠️ **NVIDIA 端点按账号开通模型**：部分模型返回 `Function … Not found for account`（404），说明该账号未开通此模型。
- **PowerShell 中文显示**：项目文件均为 UTF-8，PowerShell 5.1 直接读取可能显示乱码，用 `Get-Content -Encoding utf8` 或 VS Code 查看（流水线自身读写不受影响）。

---

## Git remote 与凭据配置（本仓库）

本仓库托管于唯一地址 **https://github.com/l1Ha/FutureTxt.git**（l1Ha 账户；
原 anfax/FutureTxt 已删除/转移，`origin` 已改指同一地址）。
本地保留 `origin` 与 `l1ha` 两个 remote 均指向它，提交后
`git push origin main && git push l1ha main` 即可同步（同仓库，第二次通常 up-to-date）。

认证在 `.git/config` 中按 URL 精确配置、绕过 Windows 凭据管理器 GCM
（**URL 必须带 `.git` 后缀才匹配**）：

```ini
[credential "https://github.com/l1Ha/FutureTxt.git"]
	helper =
	helper = "!f(){ echo username=l1Ha; echo password=$(gh auth token); };f"
```

要点：段首空 `helper =` 清掉系统级凭据管理器，再挂 `gh auth token`
（GitHub CLI 已登录 l1Ha）。**勿用 `gh auth login` 切换其它账号**，否则本 helper 失效。

**排查口诀**：`git push` 报 `Repository not found` ≠ 仓库真没了——
GCM 里只要存了凭据（哪怕已失效）就直接用、**不弹登录窗**，最容易误判：

```powershell
cmdkey /list | findstr github           # 找到用户名不对/过期的条目
cmdkey /delete:git:https://github.com   # 删掉后重推，会重新弹浏览器登录
```
清完仍 404，再用浏览器确认仓库是否已改名/转移。

---

## 注意事项

- `config.json` 含 API Key，请参考 `.gitignore`（已排除）不要提交；仓库只保留 `config.example.json`。
- 真实创作建议：先人工审阅 `00-创作概念.md` 和 `03-大纲.md`（改完再 `--force` 下一阶段），
  再让流水线批量写正文，然后走完整审校链 `review → revise → continuity`，最后 `assemble` 成书导出。
