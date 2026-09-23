"""OpenAI 兼容 API 客户端（仅使用 Python 标准库，零第三方依赖）。

配置来源优先级：环境变量 > 根目录 config.json > 默认值。
环境变量：SCIWRITE_API_KEY / SCIWRITE_BASE_URL / SCIWRITE_MODEL
"""

import json
import os
import time
import urllib.error
import urllib.request

CONFIG_FILE = "config.json"

DEFAULTS = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "temperature": 0.8,
    "max_tokens": 4096,
    "timeout": 300,
    "retries": 3,
}

_ENV_MAP = {
    "api_key": "SCIWRITE_API_KEY",
    "base_url": "SCIWRITE_BASE_URL",
    "model": "SCIWRITE_MODEL",
}


def config_path(root):
    return os.path.join(root, CONFIG_FILE)


def load_config(root):
    cfg = dict(DEFAULTS)
    path = config_path(root)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    for key, env in _ENV_MAP.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    if not cfg["api_key"]:
        raise SystemExit(
            "未配置 API Key。请运行：\n"
            "  python pipeline/run.py config --api-key <KEY> [--base-url <URL>] [--model <MODEL>]\n"
            "或设置环境变量 SCIWRITE_API_KEY（可选 SCIWRITE_BASE_URL / SCIWRITE_MODEL）。"
        )
    return cfg


def save_config(root, updates):
    path = config_path(root)
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg.update(updates)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def chat(messages, cfg, temperature=None, max_tokens=None, what=""):
    """调用 /chat/completions，返回文本内容；网络错误自动重试。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg["temperature"] if temperature is None else temperature,
        "max_tokens": int(max_tokens or cfg["max_tokens"]),
    }
    data = json.dumps(payload).encode("utf-8")
    last_err = ""
    for attempt in range(int(cfg["retries"]) + 1):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + cfg["api_key"],
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):  # 兼容分片格式
                content = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in content
                )
            return (content or "").strip()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600]
            last_err = "HTTP %s: %s" % (e.code, detail)
            if e.code not in (408, 429, 500, 502, 503, 504):
                raise RuntimeError("LLM 调用失败（%s）：%s" % (what or "未知环节", last_err))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = str(e)
        if attempt < int(cfg["retries"]):
            wait = 3 * (attempt + 1)
            print("    ! 请求失败（%s），%d 秒后重试…" % (last_err[:120], wait))
            time.sleep(wait)
    raise RuntimeError("LLM 调用重试耗尽（%s）：%s" % (what or "未知环节", last_err))
