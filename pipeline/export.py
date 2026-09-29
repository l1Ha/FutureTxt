"""多格式小说导出器（纯 Python 标准库，零第三方依赖）。

支持格式：
1. EPUB 3.0：符合 IDPF 国际标准的电子书（苹果图书、微信读书、Kindle 等完美适配，含封面、目录、排版样式）；
2. HTML 沉浸式阅读器：单文件离线网页（暗色/亮色切换、章节侧边栏目录、字数统计、阅读进度条）；
3. 标准 TXT：中文规范排版纯文本（全角缩进、装饰分割线、卷标）。
"""

from __future__ import annotations

import html
import os
import re
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple


def _word_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _md_to_paragraphs(md_text: str) -> List[str]:
    """将 Markdown 转换为段落列表，去除 Markdown 标题语法。"""
    lines = md_text.splitlines()
    paras: List[str] = []
    buf: List[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if line.startswith("#"):
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if line.startswith("---") or line.startswith("***"):
            continue
        buf.append(line)

    if buf:
        paras.append(" ".join(buf))
    return paras


def _extract_title(md_text: str, default: str) -> str:
    """从章节 Markdown 中提取标题。"""
    for line in md_text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line).strip()
    return default


def export_epub(
    output_path: str,
    title: str,
    author: str,
    description: str,
    chapters: List[Tuple[str, str]],
    keywords: Optional[List[str]] = None,
) -> str:
    """生成合规的 EPUB 3.0 / 2.0 双兼容电子书文件。

    chapters: [(章节标题, 章节正文markdown)]
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    epub_id = f"futuretxt-{int(time.time())}"
    date_str = time.strftime("%Y-%m-%d")

    css = """
body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Source Han Sans CN", serif;
    line-height: 1.85;
    margin: 5% 8%;
    color: #2c3e50;
}
h1, h2 {
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a252f;
    text-align: center;
    margin-top: 1.5em;
    margin-bottom: 1.2em;
    font-weight: 600;
}
.chapter-title {
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 0.6em;
    font-size: 1.6em;
}
p {
    text-indent: 2em;
    margin: 0.8em 0;
    text-align: justify;
}
.book-cover {
    text-align: center;
    margin-top: 25%;
}
.book-title {
    font-size: 2.2em;
    margin-bottom: 0.3em;
    color: #0f172a;
    font-weight: bold;
}
.book-author {
    font-size: 1.1em;
    color: #64748b;
    margin-bottom: 2em;
}
.book-intro {
    text-align: left;
    display: inline-block;
    max-width: 80%;
    background: #f8fafc;
    border-left: 4px solid #3b82f6;
    padding: 1.2em 1.5em;
    border-radius: 4px;
    font-size: 0.95em;
    color: #334155;
}
.book-meta {
    margin-top: 2em;
    font-size: 0.85em;
    color: #94a3b8;
}
"""

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""

    # 封面/扉页 HTML
    intro_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <div class="book-cover">
        <div class="book-title">{html.escape(title)}</div>
        <div class="book-author">作者：{html.escape(author)}</div>
        <div class="book-intro">
            <strong>【作品简介】</strong><br/>
            {html.escape(description).replace(chr(10), '<br/>')}
        </div>
        <div class="book-meta">
            全书共 {len(chapters)} 章 | FutureTxt 智能流水线导出 | {date_str}
        </div>
    </div>
</body>
</html>"""

    # 逐章 XHTML
    chapter_files: List[Tuple[str, str, str]] = []  # (filename, title, content)
    for i, (ch_title, ch_text) in enumerate(chapters, 1):
        filename = f"chapter_{i:03d}.xhtml"
        paras = _md_to_paragraphs(ch_text)
        paras_html = "\n".join(f"        <p>{html.escape(p)}</p>" for p in paras)
        ch_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
    <title>{html.escape(ch_title)}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <h1 class="chapter-title">{html.escape(ch_title)}</h1>
{paras_html}
</body>
</html>"""
        chapter_files.append((filename, ch_title, ch_html))

    # Nav XHTML
    nav_items = "\n".join(
        f'            <li><a href="{fname}">{html.escape(ctitle)}</a></li>'
        for fname, ctitle, _ in chapter_files
    )
    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head>
    <title>目录</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>目录</h1>
        <ol>
            <li><a href="cover.xhtml">扉页与简介</a></li>
{nav_items}
        </ol>
    </nav>
</body>
</html>"""

    # NCX (EPUB 2 兼容)
    ncx_points = [
        f"""    <navPoint id="navpoint-1" playOrder="1">
        <navLabel><text>扉页与简介</text></navLabel>
        <content src="cover.xhtml"/>
    </navPoint>"""
    ]
    for idx, (fname, ctitle, _) in enumerate(chapter_files, 2):
        ncx_points.append(f"""    <navPoint id="navpoint-{idx}" playOrder="{idx}">
        <navLabel><text>{html.escape(ctitle)}</text></navLabel>
        <content src="{fname}"/>
    </navPoint>""")
    ncx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="{epub_id}"/>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle><text>{html.escape(title)}</text></docTitle>
    <navMap>
{chr(10).join(ncx_points)}
    </navMap>
</ncx>"""

    # OPF Package
    manifest_items = [
        '<item id="style" href="style.css" media-type="text/css"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>',
    ]
    spine_items = [
        '<itemref idref="cover"/>',
    ]
    for i, (fname, _, _) in enumerate(chapter_files, 1):
        item_id = f"ch_{i:03d}"
        manifest_items.append(f'<item id="{item_id}" href="{fname}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="{item_id}"/>')

    opf_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookID">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="BookID">{epub_id}</dc:identifier>
        <dc:title>{html.escape(title)}</dc:title>
        <dc:creator>{html.escape(author)}</dc:creator>
        <dc:language>zh-CN</dc:language>
        <dc:description>{html.escape(description)}</dc:description>
        <dc:date>{date_str}</dc:date>
        <meta property="dcterms:modified">{time.strftime('%Y-%m-%dT%H:%M:%SZ')}</meta>
    </metadata>
    <manifest>
        {chr(10).join('        ' + x for x in manifest_items)}
    </manifest>
    <spine toc="ncx">
        {chr(10).join('        ' + x for x in spine_items)}
    </spine>
</package>"""

    # 写入 zip 文件
    with zipfile.ZipFile(output_path, "w") as zf:
        # 1. 规范要求：mimetype 必须首个入包且不压缩
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        # 2. 容器与资源
        zf.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf_content, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", ncx_content, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/cover.xhtml", intro_html, compress_type=zipfile.ZIP_DEFLATED)
        for fname, _, content in chapter_files:
            zf.writestr(f"OEBPS/{fname}", content, compress_type=zipfile.ZIP_DEFLATED)

    return output_path


def export_html(
    output_path: str,
    title: str,
    author: str,
    description: str,
    chapters: List[Tuple[str, str]],
) -> str:
    """生成完全离线的交互式单文件小说阅读器。"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    total_words = sum(_word_count(text) for _, text in chapters)

    chapters_json_items = []
    for i, (ctitle, ctext) in enumerate(chapters, 1):
        paras = _md_to_paragraphs(ctext)
        chapters_json_items.append({
            "index": i,
            "title": ctitle,
            "words": _word_count(ctext),
            "paragraphs": paras,
        })

    import json
    data_json = json.dumps({
        "title": title,
        "author": author,
        "description": description,
        "total_words": total_words,
        "chapters": chapters_json_items,
    }, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} - FutureTxt 在线阅读</title>
<style>
:root {{
    --bg-primary: #f8fafc;
    --bg-card: #ffffff;
    --text-primary: #1e293b;
    --text-secondary: #64748b;
    --border-color: #e2e8f0;
    --accent: #2563eb;
    --accent-hover: #1d4ed8;
    --sidebar-bg: #f1f5f9;
}}
[data-theme="dark"] {{
    --bg-primary: #0f172a;
    --bg-card: #1e293b;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --border-color: #334155;
    --accent: #38bdf8;
    --accent-hover: #0ea5e9;
    --sidebar-bg: #111827;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.85;
    transition: background-color 0.2s, color 0.2s;
    display: flex;
    height: 100vh;
    overflow: hidden;
}}
#sidebar {{
    width: 320px;
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    height: 100%;
    flex-shrink: 0;
}}
.sidebar-header {{
    padding: 20px;
    border-bottom: 1px solid var(--border-color);
}}
.sidebar-header h2 {{
    font-size: 1.15em;
    font-weight: 700;
    margin-bottom: 6px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.sidebar-meta {{
    font-size: 0.85em;
    color: var(--text-secondary);
}}
.chapter-list {{
    overflow-y: auto;
    flex: 1;
    list-style: none;
}}
.chapter-item {{
    padding: 12px 20px;
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    font-size: 0.95em;
    transition: background 0.15s;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.chapter-item:hover {{
    background: rgba(0,0,0,0.04);
}}
.chapter-item.active {{
    background: var(--accent);
    color: #ffffff;
    font-weight: 600;
}}
.chapter-item .ch-words {{
    font-size: 0.8em;
    opacity: 0.75;
}}
#main {{
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}}
.topbar {{
    padding: 12px 24px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg-card);
}}
.controls button {{
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.88em;
    margin-left: 8px;
    transition: 0.15s;
}}
.controls button:hover {{
    border-color: var(--accent);
    color: var(--accent);
}}
#content-container {{
    flex: 1;
    overflow-y: auto;
    padding: 40px 10%;
    display: flex;
    justify-content: center;
}}
.content-wrapper {{
    max-width: 780px;
    width: 100%;
}}
.article-header {{
    text-align: center;
    margin-bottom: 36px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border-color);
}}
.article-header h1 {{
    font-size: 1.85em;
    font-weight: 700;
    margin-bottom: 10px;
}}
.article-meta {{
    font-size: 0.9em;
    color: var(--text-secondary);
}}
.article-body p {{
    text-indent: 2em;
    margin-bottom: 1.4em;
    font-size: 1.1em;
    text-align: justify;
}}
.intro-box {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-left: 5px solid var(--accent);
    padding: 24px;
    border-radius: 8px;
    margin-bottom: 40px;
}}
.nav-buttons {{
    display: flex;
    justify-content: space-between;
    margin-top: 50px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color);
}}
.nav-btn {{
    padding: 10px 20px;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
    font-size: 0.95em;
}}
.nav-btn:disabled {{
    opacity: 0.3;
    cursor: not-allowed;
}}
@media (max-width: 768px) {{
    body {{ flex-direction: column; }}
    #sidebar {{ width: 100%; height: 200px; }}
    #content-container {{ padding: 20px 5%; }}
}}
</style>
</head>
<body>
<div id="sidebar">
    <div class="sidebar-header">
        <h2 title="{html.escape(title)}">{html.escape(title)}</h2>
        <div class="sidebar-meta">作者：{html.escape(author)} · {len(chapters)} 章 / {total_words:,} 字</div>
    </div>
    <ul class="chapter-list" id="chapterList"></ul>
</div>
<div id="main">
    <div class="topbar">
        <span id="currentChLabel">扉页与作品简介</span>
        <div class="controls">
            <button onclick="changeFontSize(-1)">A-</button>
            <button onclick="changeFontSize(1)">A+</button>
            <button onclick="toggleTheme()" id="themeBtn">🌓 切换暗色</button>
        </div>
    </div>
    <div id="content-container">
        <div class="content-wrapper" id="articleWrapper"></div>
    </div>
</div>

<script>
const book = {data_json};
let currentIndex = -1; // -1 表示简介
let fontSize = 17;

function renderSidebar() {{
    const list = document.getElementById("chapterList");
    list.innerHTML = `<li class="chapter-item ${{currentIndex === -1 ? 'active' : ''}}" onclick="goToChapter(-1)">
        <span>📖 扉页与简介</span>
    </li>`;
    book.chapters.forEach((ch, idx) => {{
        const li = document.createElement("li");
        li.className = "chapter-item" + (currentIndex === idx ? " active" : "");
        li.innerHTML = `<span>${{ch.title}}</span><span class="ch-words">${{ch.words}}字</span>`;
        li.onclick = () => goToChapter(idx);
        list.appendChild(li);
    }});
}}

function renderContent() {{
    const wrapper = document.getElementById("articleWrapper");
    const label = document.getElementById("currentChLabel");
    if (currentIndex === -1) {{
        label.innerText = "扉页与作品简介";
        wrapper.innerHTML = `
            <div class="article-header">
                <h1>${{book.title}}</h1>
                <div class="article-meta">作者：${{book.author}} | 全书约 ${{book.total_words.toLocaleString()}} 字</div>
            </div>
            <div class="intro-box">
                <h3 style="margin-bottom:12px;color:var(--accent);">作品概念与梗概</h3>
                <div style="white-space: pre-wrap; line-height:1.75;">${{book.description}}</div>
            </div>
            <div class="nav-buttons">
                <button class="nav-btn" disabled>上一章</button>
                <button class="nav-btn" onclick="goToChapter(0)">开始阅读第一章 →</button>
            </div>
        `;
    }} else {{
        const ch = book.chapters[currentIndex];
        label.innerText = ch.title;
        const pTags = ch.paragraphs.map(p => `<p style="font-size: ${{fontSize}}px;">${{p}}</p>`).join("");
        wrapper.innerHTML = `
            <div class="article-header">
                <h1>${{ch.title}}</h1>
                <div class="article-meta">第 ${{ch.index}} 章 | ${{ch.words}} 字</div>
            </div>
            <div class="article-body">
                ${{pTags}}
            </div>
            <div class="nav-buttons">
                <button class="nav-btn" onclick="goToChapter(currentIndex - 1)">← 上一章</button>
                <button class="nav-btn" onclick="goToChapter(currentIndex + 1)" ${{currentIndex >= book.chapters.length - 1 ? 'disabled' : ''}}>下一章 →</button>
            </div>
        `;
    }}
    document.getElementById("content-container").scrollTop = 0;
}}

function goToChapter(idx) {{
    if (idx < -1 || idx >= book.chapters.length) return;
    currentIndex = idx;
    renderSidebar();
    renderContent();
}}

function toggleTheme() {{
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    document.getElementById("themeBtn").innerText = next === "dark" ? "☀️ 亮色模式" : "🌓 暗色模式";
}}

function changeFontSize(delta) {{
    fontSize = Math.max(14, Math.min(26, fontSize + delta));
    const paras = document.querySelectorAll(".article-body p");
    paras.forEach(p => p.style.fontSize = fontSize + "px");
}}

renderSidebar();
renderContent();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path


def export_txt(
    output_path: str,
    title: str,
    author: str,
    description: str,
    chapters: List[Tuple[str, str]],
) -> str:
    """生成符合中文网文排版规范的纯文本 TXT。"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    total_words = sum(_word_count(text) for _, text in chapters)

    lines: List[str] = [
        f"《{title}》",
        f"作者：{author}",
        f"全书规模：{len(chapters)} 章 / 约 {total_words} 字",
        f"生成日期：{time.strftime('%Y-%m-%d')}",
        "=" * 48,
        "【作品简介】",
        description.strip(),
        "=" * 48,
        "",
    ]

    for i, (ctitle, ctext) in enumerate(chapters, 1):
        lines.append(f"\n\n{'=' * 20} {ctitle} {'=' * 20}\n")
        paras = _md_to_paragraphs(ctext)
        for p in paras:
            # 中文全角空格标准段首缩进
            lines.append(f"\u3000\u3000{p}")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return output_path


def export_all(
    proj: Any,
    formats: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """一键为项目导出指定格式小说。

    formats 默认为 ['epub', 'html', 'txt']
    """
    if formats is None or "all" in formats:
        formats = ["epub", "html", "txt"]

    cfg = proj.config()
    title = cfg.get("title", proj.name)
    author = cfg.get("author", "FutureTxt AI Writer")
    concept_raw = ""
    concept_path = proj.f_concept()
    if os.path.exists(concept_path):
        with open(concept_path, encoding="utf-8") as f:
            concept_raw = f.read()

    # 提取简介
    m_intro = re.search(r"## 故事前提展开[^\n]*\n([\s\S]*?)(?=\n##|$)", concept_raw)
    description = m_intro.group(1).strip() if m_intro else (cfg.get("premise") or title)

    # 收集章节
    chapter_files = proj.list_chapters()
    if not chapter_files:
        raise RuntimeError("项目尚无章节文件，请先执行 draft 阶段生成正文。")

    chapters: List[Tuple[str, str]] = []
    for path in chapter_files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        no = re.search(r"chapter_(\d+)", os.path.basename(path))
        def_title = f"第 {int(no.group(1))} 章" if no else os.path.basename(path)
        ch_title = _extract_title(text, def_title)
        chapters.append((ch_title, text))

    dist_dir = proj.path("dist")
    os.makedirs(dist_dir, exist_ok=True)
    results = {}

    for fmt in formats:
        fmt = fmt.lower().strip()
        if fmt == "epub":
            out_file = os.path.join(dist_dir, f"{title}.epub")
            export_epub(out_file, title, author, description, chapters)
            results["epub"] = out_file
        elif fmt == "html":
            out_file = os.path.join(dist_dir, f"{title}.html")
            export_html(out_file, title, author, description, chapters)
            results["html"] = out_file
        elif fmt == "txt":
            out_file = os.path.join(dist_dir, f"{title}.txt")
            export_txt(out_file, title, author, description, chapters)
            results["txt"] = out_file

    return results
