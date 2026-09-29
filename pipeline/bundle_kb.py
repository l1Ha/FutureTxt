"""将 32 篇知识库编译为适合前端快速加载与检索的 JSON 数据包。"""

from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(ROOT, "knowledge")
WEB_DIR = os.path.join(ROOT, "web")


def build_knowledge_bundle() -> dict:
    os.makedirs(WEB_DIR, exist_ok=True)
    bundle = {
        "categories": {},
        "files": [],
        "total_chars": 0,
    }

    for cat in sorted(os.listdir(KB_DIR)):
        cat_path = os.path.join(KB_DIR, cat)
        if not os.path.isdir(cat_path):
            continue
        bundle["categories"][cat] = []
        for fname in sorted(os.listdir(cat_path)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(cat_path, fname)
            with open(fpath, encoding="utf-8") as fp:
                content = fp.read()
            # 提取一级和二级标题作为提纲
            headings = re.findall(r"^(#{1,3})\s+(.+)$", content, re.M)
            outline_headers = [h[1].strip() for h in headings]

            file_item = {
                "category": cat,
                "filename": fname,
                "title": fname.replace(".md", "").split("-", 1)[-1],
                "char_count": len(content),
                "headers": outline_headers,
                "content": content,
            }
            bundle["categories"][cat].append(fname)
            bundle["files"].append(file_item)
            bundle["total_chars"] += len(content)

    out_path = os.path.join(WEB_DIR, "knowledge_bundle.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(bundle, fp, ensure_ascii=False)

    size_kb = round(os.path.getsize(out_path) / 1024, 1)
    print(f"✓ 知识库编译完成: {out_path} ({len(bundle['files'])} 篇文档, {bundle['total_chars']} 字符, 体积: {size_kb} KB)")
    return bundle


if __name__ == "__main__":
    build_knowledge_bundle()
