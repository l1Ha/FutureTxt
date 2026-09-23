"""知识库加载器：把 knowledge/ 下的相关模块注入到各阶段提示词中。"""

import os

KB_DIRNAME = "knowledge"

# 每个流水线阶段需要引用的知识模块（按相对路径子串匹配）
STAGE_MODULES = {
    "concept": ["01-概论", "07-素材与创意"],
    "world": ["01-概论/02", "02-世界观", "03-科学顾问"],
    "characters": ["04-角色", "02-世界观/06"],
    "outline": ["05-情节结构", "07-素材与创意", "01-概论/03"],
    "draft": ["06-文风与叙事", "05-情节结构", "04-角色/03", "02-世界观/02", "08-参考/02"],
    "review": ["08-参考/03", "03-科学顾问"],
    "revise": ["06-文风与叙事", "05-情节结构"],
}

DEFAULT_CAP = 16000  # 单阶段注入知识的总字符上限


def kb_root(root):
    return os.path.join(root, KB_DIRNAME)


def list_files(root):
    base = kb_root(root)
    out = []
    for dirpath, _dirs, files in os.walk(base):
        for name in sorted(files):
            if name.endswith(".md"):
                out.append(os.path.join(dirpath, name))
    out.sort()
    return out


def _matched(root, keys):
    """返回 [(匹配顺序, 文件路径)]，按 keys 的优先级排序。"""
    hits = []
    for path in list_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        for i, key in enumerate(keys):
            if key in rel:
                hits.append((i, rel, path))
                break
    hits.sort(key=lambda t: (t[0], t[1]))
    return hits


def load(root, keys, cap=DEFAULT_CAP):
    """读取匹配的知识文件，拼接为一段可注入提示词的文本。"""
    parts, used = [], 0
    for _i, rel, path in _matched(root, keys):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            continue
        remain = cap - used
        if remain <= 0:
            break
        if len(text) > remain:
            text = text[:remain] + "\n…（本篇因长度截断）"
        parts.append("### 知识库文档：%s\n%s" % (rel.replace("knowledge/", ""), text))
        used += len(text)
    if not parts:
        return ""
    return "\n\n".join(parts)


def search(root, keyword, limit=30):
    """朴素关键词检索，返回 [(相对路径, 行号, 行内容)]。"""
    kw = keyword.lower()
    hits = []
    for path in list_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as f:
                for no, line in enumerate(f, 1):
                    if kw in line.lower():
                        hits.append((rel, no, line.strip()))
                        if len(hits) >= limit:
                            return hits
        except OSError:
            continue
    return hits
