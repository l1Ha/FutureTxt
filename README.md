# FutureTxt —— 科幻小说知识库 + 自动化创作流水线

一个面向中文科幻长篇的创作系统：**32 篇方法论知识库** 会被自动注入 **8 阶段 LLM 流水线**，
从一句题材关键词一路产出「概念 → 世界观 → 角色 → 大纲 → 逐章正文 → 逐章审校 → 修订 → 汇编成书」。

纯 Python 标准库实现（Python 3.8+），零第三方依赖，Windows / macOS / Linux 通用。

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
│   ├── run.py                 # 命令行入口
│   ├── stages.py              # 8 个阶段的提示词与执行逻辑
│   ├── llm.py                 # OpenAI 兼容 API 客户端（重试、UTF-8）
│   └── kb.py                  # 知识库加载与检索（按阶段注入相关模块）
├── projects/<项目名>/         # 每本小说一个目录
│   ├── project.json           # 书名、题材、章节数、文风等配置
│   ├── state.json             # 阶段状态与章节摘要（断点续跑）
│   ├── 00-创作概念.md          # 阶段产物
│   ├── 01-世界观.md            #   含「硬性设定 W1、W2…」铁律清单
│   ├── 02-角色.md              #   含「角色一致性要点 C1、C2…」
│   ├── 03-大纲.md              #   每章目标/冲突/转折/伏笔/钩子，机器可解析
│   ├── chapters/chapter_001.md #  逐章正文（修订前自动存 .bak）
│   ├── reviews/chapter_001_审校.md
│   └── manuscript/《书名》·初稿.md
├── config.json                # LLM API 配置（不入库密钥，见下）
└── README.md
```

## 快速开始

```powershell
# 1. 配置 API（任何 OpenAI 兼容接口均可：OpenAI / DeepSeek / 月之暗面 / 通义 / 本地 vLLM…）
python pipeline/run.py config --api-key sk-xxx `
    --base-url https://api.openai.com/v1 --model gpt-4o-mini
#   或用环境变量：SCIWRITE_API_KEY / SCIWRITE_BASE_URL / SCIWRITE_MODEL

# 2. 创建项目
python pipeline/run.py init 赛博侦探 `
    --keywords "赛博朋克,侦探,记忆交易" `
    --premise "在记忆可以买卖的城市里，一名侦探发现所有案件都指向自己被删掉的过去" `
    --chapters 20 --words 3000 --pov "第三人称有限" --tone "冷峻、克制"

# 3. 一键跑完全流程
python pipeline/run.py run 赛博侦探

# 4. 查看进度
python pipeline/run.py status 赛博侦探
```

## 流水线阶段

| 阶段 | 产物 | 说明 |
|---|---|---|
| `concept` | 00-创作概念.md | logline、三层冲突、主题、创新点、书名候选 |
| `world` | 01-世界观.md | 科技/时间线/地理/社会/文化 + **硬性设定 W1…Wn**（后续写作与审校的铁律） |
| `characters` | 02-角色.md | 欲望-需求-缺陷-弧光-语言指纹 + **一致性要点 C1…Cn** |
| `outline` | 03-大纲.md | 精确 N 章，每章：场景/目标/冲突/转折/揭示/伏笔/钩子 |
| `draft` | chapters/*.md | 逐章生成：注入知识库+世界观+角色+邻章大纲+前情摘要+上一章结尾 |
| `review` | reviews/*_审校.md | 对照 72 条审稿清单与硬性设定逐章打分、列问题 |
| `revise` | 覆盖正文（.bak 备份） | 按审校报告重写；结论为「可直接通过」的章节自动跳过 |
| `assemble` | manuscript/《书名》·初稿.md | 合并全书、加扉页与字数统计 |

### 常用命令

```powershell
python pipeline/run.py run 赛博侦探 --stages draft --only 1-10   # 只写第 1~10 章
python pipeline/run.py run 赛博侦探 --stages review --only 3     # 只审第 3 章
python pipeline/run.py run 赛博侦探 --stages revise --force      # 强制修订已通过的章节
python pipeline/run.py run 赛博侦探 --stages outline --force     # 重做大纲
python pipeline/run.py run 赛博侦探 --stages assemble            # 重新汇编
python pipeline/run.py run 赛博侦探 --stages draft --only 7,9-12 # 逗号+区间混合
python pipeline/run.py kb 黑暗森林                               # 全文检索知识库
python pipeline/run.py kb                                        # 列出全部知识库文件
```

### 断点续跑

所有阶段均检查产物是否存在：中断后重跑同一命令会**自动跳过已完成部分**（正文按章节文件存在判断，
世界观等按文件存在判断，`--force` 可重做）。每章生成后会记录 120 字剧情摘要到 `state.json`，
供后续章节衔接，全书任意位置续写都保留上下文。

## 知识库如何被使用

`pipeline/kb.py` 按阶段映射注入相关模块（单阶段上限 1.4~2 万字符，超长文件保头保尾，
确保文末的「硬性设定」「要点速查」不被截掉）：

- `concept` ← 01-概论、07-素材与创意
- `world` ← 02-世界观全册、03-科学顾问全册
- `characters` ← 04-角色、文化日常篇
- `outline` ← 05-情节结构、07-素材与创意
- `draft` ← 06-文风与叙事、05-情节结构、对话篇、科技可信度、术语表
- `review` ← 08-参考/03-审稿自查清单（72 条）、03-科学顾问

也可以脱离流水线，直接把这些文档当作写作参考，或复制其中的提示词手工使用。

## 配置说明

`config.json`（由 `run.py config` 写入）：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `base_url` | `https://api.openai.com/v1` | 任意 OpenAI 兼容接口根地址 |
| `api_key` | 空 | 也可用环境变量 `SCIWRITE_API_KEY` |
| `model` | `gpt-4o-mini` | 建议长篇章节用中等以上模型 |
| `temperature` | 0.8 | 创作温度 |
| `max_tokens` | 4096 | 单次输出上限（正文会自动按每章字数放大） |
| `timeout` / `retries` | 300 / 3 | 秒 / 429·5xx 自动重试次数 |

`projects/<名>/project.json`（由 `run.py init` 生成）：`title`、`keywords`、`premise`、
`target_chapters`、`words_per_chapter`、`pov`、`tone`、`audience`、`extra`。
建好后可直接改这个文件再 `--force` 重跑对应阶段。

## 注意事项

- `config.json` 含 API Key，请参考 `.gitignore`（已排除）不要提交；仓库只保留 `config.example.json`。
- `projects/测试项目` 是用本地模拟接口跑通全流程的**结构示例**，内容为占位文本，可直接删除。
- 真实创作建议：先人工审阅 `00-创作概念.md` 和 `03-大纲.md`（改完再 `--force` 下一阶段），
  再让流水线批量写正文，最后逐章 `review → revise`。
