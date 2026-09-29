"""FutureTxt 环境与服务自检诊断工具（纯标准库，零第三方依赖）。

用于在创作前全面体检：
1. Python 版本与系统环境；
2. 32 篇科幻方法论知识库完整性；
3. LLM API 连通性、网络时延与模型可用性；
4. 项目工作区与读写权限。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple


def check_python_environment() -> Dict[str, Any]:
    ver = sys.version_info
    ok = ver >= (3, 8)
    return {
        "ok": ok,
        "version": f"{ver.major}.{ver.minor}.{ver.micro}",
        "platform": sys.platform,
        "encoding": sys.getdefaultencoding(),
    }


def check_knowledge_base(root: str) -> Dict[str, Any]:
    kb_dir = os.path.join(root, "knowledge")
    if not os.path.isdir(kb_dir):
        return {"ok": False, "total_files": 0, "categories": {}, "error": "knowledge 目录不存在"}

    categories: Dict[str, int] = {}
    total_files = 0
    total_chars = 0

    for cat in sorted(os.listdir(kb_dir)):
        cat_path = os.path.join(kb_dir, cat)
        if os.path.isdir(cat_path):
            files = [f for f in os.listdir(cat_path) if f.endswith(".md")]
            categories[cat] = len(files)
            total_files += len(files)
            for f in files:
                try:
                    with open(os.path.join(cat_path, f), encoding="utf-8") as fp:
                        total_chars += len(fp.read())
                except OSError:
                    pass

    # 预期 8 个大类，32 篇核心指南
    ok = total_files >= 30
    return {
        "ok": ok,
        "total_files": total_files,
        "total_chars": total_chars,
        "categories": categories,
    }


def check_api_connectivity(root: str) -> Dict[str, Any]:
    import llm
    try:
        cfg = llm.load_config(root)
    except Exception as e:
        return {"ok": False, "configured": False, "error": str(e)}

    base_url = cfg.get("base_url", "").rstrip("/")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "")

    if not api_key:
        return {"ok": False, "configured": False, "error": "未设置 API Key"}

    # 发起极轻量级探测请求（5 个 token）
    url = f"{base_url}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
        "temperature": 0.1,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = time.time() - t0
            raw = resp.read().decode("utf-8", "replace")
            _body = json.loads(raw)
            return {
                "ok": True,
                "configured": True,
                "model": model,
                "base_url": base_url,
                "latency_sec": round(elapsed, 2),
            }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        err_msg = e.read().decode("utf-8", "replace")[:200]
        return {
            "ok": False,
            "configured": True,
            "model": model,
            "base_url": base_url,
            "latency_sec": round(elapsed, 2),
            "error": f"HTTP {e.code}: {err_msg}",
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "ok": False,
            "configured": True,
            "model": model,
            "base_url": base_url,
            "latency_sec": round(elapsed, 2),
            "error": str(e),
        }


def run_doctor(root: str) -> str:
    """运行全系统健康体检并输出报告。"""
    lines = []
    lines.append(f"╔{'═' * 58}╗")
    lines.append(f"║ FutureTxt 创作系统环境体检与连通性自检报告                ║")
    lines.append(f"╚{'═' * 58}╝\n")

    # 1. Python 环境
    py = check_python_environment()
    if py["ok"]:
        lines.append(f"  [✓] Python 运行环境：Python {py['version']} on {py['platform']} ({py['encoding']})")
    else:
        lines.append(f"  [✗] Python 运行环境：Python {py['version']}（建议 Python 3.8+）")

    # 2. 知识库
    kb = check_knowledge_base(root)
    if kb["ok"]:
        lines.append(f"  [✓] 知识库完整性：共 {kb['total_files']} 篇文档（{kb['total_chars']:,} 字符，涵盖 {len(kb['categories'])} 个方法论分类）")
    else:
        lines.append(f"  [!] 知识库状态：共 {kb['total_files']} 篇文档（部分缺失）")

    # 3. 存储与权限
    proj_dir = os.path.join(root, "projects")
    os.makedirs(proj_dir, exist_ok=True)
    can_write = os.access(proj_dir, os.W_OK)
    if can_write:
        existing_projs = [d for d in os.listdir(proj_dir) if os.path.isdir(os.path.join(proj_dir, d))]
        lines.append(f"  [✓] 项目存储区：{proj_dir}（正常可写，已包含 {len(existing_projs)} 个小说项目）")
    else:
        lines.append(f"  [✗] 项目存储区：{proj_dir}（写权限受限）")

    # 4. API 连通性
    api = check_api_connectivity(root)
    if not api.get("configured"):
        lines.append(f"  [!] LLM API 配置：尚未配置 API Key（提示：可使用 pipeline/run.py config 配置）")
    elif api["ok"]:
        lines.append(f"  [✓] LLM 服务连通：{api['model']} @ {api['base_url']}（响应正常，时延 {api['latency_sec']}s）")
    else:
        lines.append(f"  [✗] LLM 服务连通异常：{api.get('error')}（模型: {api.get('model')}）")

    lines.append("\n" + "=" * 60)
    if py["ok"] and kb["ok"] and can_write:
        lines.append("系统运行就绪，随时可以开展科幻创作！")
    else:
        lines.append("请根据以上标记项进行排查修复。")

    return "\n".join(lines)
