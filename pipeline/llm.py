"""OpenAI 兼容 API 客户端（仅使用 Python 标准库，零第三方依赖）。

配置来源优先级：环境变量 > 根目录 config.json > 默认值。
环境变量：SCIWRITE_API_KEY / SCIWRITE_BASE_URL / SCIWRITE_MODEL
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

CONFIG_FILE = "config.json"

DEFAULTS: Dict[str, Any] = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "temperature": 0.8,
    "max_tokens": 4096,
    "timeout": 600,
    "retries": 5,
    "headers": {},
    "extra_params": {},
}

_ENV_MAP = {
    "api_key": "SCIWRITE_API_KEY",
    "base_url": "SCIWRITE_BASE_URL",
    "model": "SCIWRITE_MODEL",
}

# 全局记录最近一次调用的 Token 用量
_LAST_USAGE: Dict[str, int] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}


class LLMError(RuntimeError):
    """LLM 调用基础异常。"""


class LLMConfigError(LLMError):
    """配置缺失或无效。"""


class LLMTokenExhaustedError(LLMError):
    """输出被截断或思考 token 耗尽正文。"""


class LLMNetworkError(LLMError):
    """网络或端点服务异常。"""


def get_last_usage() -> Dict[str, int]:
    """获取最近一次请求消耗的 Token 数。"""
    return dict(_LAST_USAGE)


def config_path(root: str) -> str:
    return os.path.join(root, CONFIG_FILE)


def load_config(root: str) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    path = config_path(root)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    for key, env in _ENV_MAP.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    if not cfg["api_key"]:
        raise LLMConfigError(
            "未配置 API Key。请运行：\n"
            "  python pipeline/run.py config --api-key <KEY> [--base-url <URL>] [--model <MODEL>]\n"
            "或设置环境变量 SCIWRITE_API_KEY（可选 SCIWRITE_BASE_URL / SCIWRITE_MODEL）。"
        )
    return cfg


def save_config(root: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    path = config_path(root)
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg.update(updates)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def _extract(raw: str) -> Tuple[str, Dict[str, int]]:
    """从 SSE 流式响应或普通 JSON 响应中提取文本与 token 用量统计。"""
    text = raw.lstrip("\ufeff \t\r\n")
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if text.startswith("data:"):  # SSE 流
        parts: List[str] = []
        done = False
        parts_reasoning = False
        finish = None

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

            # 提取 usage 统计（如果端点在流尾输出 usage）
            if "usage" in j and isinstance(j["usage"], dict):
                u = j["usage"]
                usage["prompt_tokens"] = int(u.get("prompt_tokens") or 0)
                usage["completion_tokens"] = int(u.get("completion_tokens") or 0)
                usage["total_tokens"] = int(u.get("total_tokens") or (usage["prompt_tokens"] + usage["completion_tokens"]))

            choices = j.get("choices") or [{}]
            ch = choices[0] if choices else {}
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]

            delta = ch.get("delta") or {}
            if delta.get("reasoning_content"):
                parts_reasoning = True
            c = delta.get("content")
            if isinstance(c, str) and c:
                parts.append(c)
            elif isinstance(c, list):
                parts.append("".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in c
                ))

        out = "".join(parts)
        if out:
            if finish == "length":
                raise LLMTokenExhaustedError("输出被 max_tokens 截断（需加倍重试）")
            return out, usage
        if done:
            if parts_reasoning:
                raise LLMTokenExhaustedError("思考占满 max_tokens，正文为空（已自动加倍重试）")
            raise LLMError("模型返回内容为空")
        raise LLMNetworkError("流式响应被意外截断")

    # 非流式回退
    body = json.loads(text)
    if "usage" in body and isinstance(body["usage"], dict):
        u = body["usage"]
        usage["prompt_tokens"] = int(u.get("prompt_tokens") or 0)
        usage["completion_tokens"] = int(u.get("completion_tokens") or 0)
        usage["total_tokens"] = int(u.get("total_tokens") or (usage["prompt_tokens"] + usage["completion_tokens"]))

    ch0 = (body.get("choices") or [{}])[0]
    msg = ch0.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    content = (content or "").strip()
    if ch0.get("finish_reason") == "length" and content:
        raise LLMTokenExhaustedError("输出被 max_tokens 截断（需加倍重试）")
    return content, usage


def chat(
    messages: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    what: str = "",
    return_usage: bool = False,
) -> Union[str, Tuple[str, Dict[str, int]]]:
    """调用 /chat/completions（默认启用流式以维持活跃连接）。

    网络错误自动重试；输出截断自动扩充 max_tokens 并重试。
    """
    global _LAST_USAGE
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    current_max_tokens = int(max_tokens or cfg.get("max_tokens", 4096))

    payload: Dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg["temperature"] if temperature is None else temperature,
        "max_tokens": current_max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    for k, v in (cfg.get("extra_params") or {}).items():
        payload.setdefault(k, v)

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "Accept": "text/event-stream, application/json",
    }
    # 自定义额外请求头
    for hk, hv in (cfg.get("headers") or {}).items():
        headers[hk] = str(hv)

    last_err = ""
    retries = int(cfg.get("retries", 5))

    for attempt in range(retries + 1):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=cfg.get("timeout", 600)) as resp:
                raw = resp.read().decode("utf-8", "replace")
            content, usage = _extract(raw)
            _LAST_USAGE = usage
            if return_usage:
                return content, usage
            return content

        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600]
            last_err = f"HTTP {e.code}: {detail}"

            # 部分端点不支持 stream_options，剔除后重试
            if e.code == 400 and "stream_options" in payload:
                payload.pop("stream_options", None)
                continue

            # 端点不支持流式降级
            if e.code == 400 and payload.get("stream") and "stream" in detail.lower():
                payload["stream"] = False
                payload.pop("stream_options", None)
                continue

            # 不可重试的客户端错误直接抛出
            if e.code not in (408, 429, 500, 502, 503, 504):
                raise LLMNetworkError(f"LLM 调用失败（{what or '未知环节'}）：{last_err}") from e

        except (urllib.error.URLError, TimeoutError, OSError, ValueError, LLMError) as e:
            last_err = str(e)
            if ("加倍重试" in last_err or isinstance(e, LLMTokenExhaustedError)) and payload["max_tokens"] < 32000:
                payload["max_tokens"] = min(payload["max_tokens"] * 2, 32000)
                print(f"    · max_tokens 加倍至 {payload['max_tokens']} 后重试")
                continue

        if attempt < retries:
            wait = min(3 * (attempt + 1), 30)
            print(f"    ! 请求失败（{last_err[:120]}），{wait} 秒后重试…")
            time.sleep(wait)

    raise LLMNetworkError(f"LLM 调用重试耗尽（{what or '未知环节'}）：{last_err}")
