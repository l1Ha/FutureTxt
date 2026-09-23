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
    "timeout": 600,
    "retries": 5,
    "extra_params": {},
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


def _extract(raw):
    """从 SSE 流式响应或普通 JSON 响应中提取文本。"""
    text = raw.lstrip("﻿ \t\r\n")
    if text.startswith("data:"):  # SSE 流
        parts, done = [], False
        parts_reasoning = False
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                done = True
                continue
            try:
                j = json.loads(data)
            except ValueError:
                continue
            ch = (j.get("choices") or [{}])[0]
            delta = ch.get("delta") or {}
            if delta.get("reasoning_content"):
                parts_reasoning = True
            c = delta.get("content")
            if isinstance(c, str) and c:
                parts.append(c)
            elif isinstance(c, list):
                parts.append("".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in c))
        out = "".join(parts)
        if out:
            return out
        if done:
            if parts_reasoning:
                raise ValueError("思考占满 max_tokens，正文为空（已自动加倍重试）")
            raise ValueError("返回内容为空")
        raise ValueError("流式响应被截断")
    body = json.loads(text)  # 非流式回退
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):  # 分片格式
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return (content or "").strip()


def chat(messages, cfg, temperature=None, max_tokens=None, what=""):
    """调用 /chat/completions（流式），返回文本内容；网络错误自动重试。

    使用流式请求是为了保持连接持续有数据流动，避免长生成期间被
    中间网络设备掐断（WinError 10054）。
    """
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg["temperature"] if temperature is None else temperature,
        "max_tokens": int(max_tokens or cfg["max_tokens"]),
        "stream": True,
    }
    for k, v in (cfg.get("extra_params") or {}).items():  # 如 reasoning_effort 等端点扩展参数
        payload.setdefault(k, v)
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["api_key"],
        "Accept": "text/event-stream, application/json",
    }
    last_err = ""
    retries = int(cfg["retries"])
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
                raw = resp.read().decode("utf-8", "replace")
            return _extract(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600]
            last_err = "HTTP %s: %s" % (e.code, detail)
            if e.code == 400 and payload.get("stream") and "stream" in detail.lower():
                payload["stream"] = False  # 端点不支持流式，降级为普通请求
                data = json.dumps(payload).encode("utf-8")
                continue
            if e.code not in (408, 429, 500, 502, 503, 504):
                raise RuntimeError("LLM 调用失败（%s）：%s" % (what or "未知环节", last_err))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last_err = str(e)
            if "思考占满" in last_err and payload["max_tokens"] < 32000:
                payload["max_tokens"] = min(payload["max_tokens"] * 2, 32000)
                data = json.dumps(payload).encode("utf-8")
                print("    · max_tokens 加倍至 %d 后重试" % payload["max_tokens"])
                continue
        if attempt < retries:
            wait = min(3 * (attempt + 1), 30)
            print("    ! 请求失败（%s），%d 秒后重试…" % (last_err[:120], wait))
            time.sleep(wait)
    raise RuntimeError("LLM 调用重试耗尽（%s）：%s" % (what or "未知环节", last_err))
