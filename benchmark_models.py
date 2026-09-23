# -*- coding: utf-8 -*-
"""候选模型横测：延迟 + 中文创作质量。"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import llm

PROMPT = ("写一个200字内的科幻场景：侦探在记忆交易黑市醒来，发现自己的记忆被标价出售。"
          "要求有感官细节和一句对话。只输出正文。")

MODELS = [
    "z-ai/glm-5.3",
    "moonshotai/kimi-k3",
    "deepseek-ai/deepseek-v4.1-flash",
    "nvidia/nemotron-3-super-120b-a12b",
    "mistralai/mistral-large-2-instruct",
]

api = llm.load_config(os.path.dirname(os.path.abspath(__file__)))
for m in MODELS:
    cfg = dict(api, model=m)
    t0 = time.time()
    try:
        out = llm.chat([{"role": "user", "content": PROMPT}], cfg,
                       temperature=0.9, max_tokens=1500, what=m)
        print("=== [%.1fs] %s ===" % (time.time() - t0, m))
        print(out[:600].strip() or "(空)")
    except Exception as e:
        print("=== [%.1fs] %s === FAILED: %s" % (time.time() - t0, m, str(e)[:200]))
    print()
