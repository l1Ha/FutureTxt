# FutureTxt —— 科幻小说知识库 + 自动化创作流水线

面向中文长篇科幻小说的专业创作系统：**32 篇独家方法论知识库** 动态注入 **8 阶段智能创作流水线**，
从一句题材关键词一路产出「概念 → 世界观 → 角色 → 大纲 → 逐章正文 → 逐章审校 → 修订 → 汇编成书 → 出版级导出（EPUB / HTML / TXT）」。

**纯 Python 标准库实现（Python 3.8+），零第三方依赖，跨平台（Windows / macOS / Linux）通用。**

---

## 核心亮点与系统能力

- 🧠 **32 篇科幻方法论知识库**：涵盖概论、硬核世界观自上而下因果推演、7大科学顾问（物理/天文/生物/AI/工程/医学/社会学）、角色语言指纹、悬念伏笔闭环与 72 条审稿清单。
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
├── knowledge/                 # 科幻写作知识库（32 篇，完整版）
│   ├── 01-概论/               # 定义与历史、子类型全景、思想实验
│   ├── 02-世界观/             # 构建方法、科技可信度、社会、时间线、地理、文化日常
│   ├── 03-科学顾问/           # 物理、天文、生物、AI、工程、医学、社会学
│   ├── 04-角色/               # 角色构建、反派与对立力量、对话与语言指纹
│   ├── 05-情节结构/           # 整体结构与节奏、章节与钩子、悬念与信息释放
│   ├── 06-文风与叙事/         # 视角、描写沉浸感、解释性写作（infodump 替代）
│   ├── 07-素材与创意/         # 灵感方法、常见套路清单、反套路创新
│   └── 08-参考/               # 经典作品分析、术语表、审稿自查清单、获奖书单
├── pipeline/                  # 自动化流水线
│   ├── run.py                 # 统一命令行入口（支持彩色终端与多子命令）
│   ├── stages.py              # 8 阶段提示词工程、状态记忆池与执行逻辑
│   ├── llm.py                 # 生产级 OpenAI 兼容客户端（流式保活、用量追踪、截断扩充）
│   ├── kb.py                  # 知识库均衡预算加载、智能分词检索与局部动态 RAG
│   ├── export.py              # 纯标准库 EPUB 3.0 / 单文件 HTML 阅读器 / 规范 TXT 导出
│   ├── analytics.py           # 小说全景字数统计、对白占比、篇幅分布柱状图、角色聚光灯
│   ├── audit.py               # 设定圣经 W/C 规则与大纲伏笔闭环一致性审计
│   └── doctor.py              # 全系统环境、知识库完整性与端点连通性自检
├── tests/                     # 自动化单元测试套件（零外部依赖，一键运行）
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
│   ├── manuscript/《书名》·初稿.md # 全书汇编稿
│   └── dist/                  # 出版交付物（.epub / .html / .txt）
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

### 4. 一键跑通全流程
```bash
python pipeline/run.py run 赛博侦探
```

### 5. 查看进度与 Token 消耗
```bash
python pipeline/run.py status 赛博侦探
```

---

## 流水线 8 阶段

| 阶段 | 产物 | 知识库注入重点 | 说明 |
|---|---|---|---|
| `concept` | 00-创作概念.md | 概论、素材与创意 | 确立 Logline、三层冲突、思想实验、结局与创新点 |
| `world` | 01-世界观.md | 世界观、科学顾问全册 | 科技/时间线/地理/社会/文化 + **硬性设定 W1…Wn** 铁律清单 |
| `characters` | 02-角色.md | 角色构建、文化日常 | 欲望/需求/缺陷/语言指纹 + **角色一致性 C1…Cn** |
| `outline` | 03-大纲.md | 情节结构、反套路策略 | 精确 N 章三幕式展开：目标/冲突/转折/信息揭示/伏笔/钩子 |
| `draft` | chapters/*.md | 文风叙事、动态科学片段 | 逐章创作：前情摘要 + 邻章大纲 + 上章结尾衔接 + 局部针对性 RAG |
| `review` | reviews/*_审校.md | 72条审稿清单、科学顾问 | 责任编辑视角：对照硬规则打分（1-10）、指出具体缺陷与修改建议 |
| `revise` | 覆盖正文（.bak备份） | 文风叙事、情节结构 | 针对性重写；若审校结论为「可直接通过」则智能跳过 |
| `assemble` | manuscript/初稿.md + dist/* | 全书合并 | 汇编全书，并自动生成 EPUB、HTML 与 TXT 出版交付件 |

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

### 4. 灵活分步与区间控制
```bash
python pipeline/run.py run 赛博侦探 --stages draft --only 1-5     # 仅写第 1~5 章
python pipeline/run.py run 赛博侦探 --stages review --only 3       # 仅审第 3 章
python pipeline/run.py run 赛博侦探 --stages revise --force        # 强制修订
python pipeline/run.py run 赛博侦探 --stages outline --force       # 重做大纲
python pipeline/run.py run 赛博侦探 --stages assemble              # 重新汇编与导出
```

### 5. 知识库智能检索
```bash
python pipeline/run.py kb 戴森球       # 检索知识库，按相关度权重展示高匹配段落
python pipeline/run.py kb 曲率引擎
python pipeline/run.py kb              # 列出全部 32 篇方法论文档
```

---

## 运行自动化测试

本项目坚持零第三方依赖原则，所有测试均使用 Python 标准库 `unittest`：

```bash
python -m unittest discover tests
```
*包含 LLM 客户端容错、知识库均衡加载、大纲切分、EPUB 电子书封装、小说数据统计与一致性审计等 22 项全功能单元测试。*

---

## 模型实测建议

- 推荐使用非推理大参数模型（如 `nvidia/nemotron-3-super-120b-a12b`、`gpt-4o`、`deepseek-chat`）以获得最平稳的中文正文输出速度。
- 若选用推理模型（如 DeepSeek-R1、GLM-Zero、Kimi），系统已内置 `reasoning_content` 截断防护，遇到思考耗尽时将自动加倍扩展 `max_tokens`（上限 32000）并安全重试。
