# -*- coding: utf-8 -*-
"""无 TeX 依赖的 PDF 导出（纯 Python 标准库）。

做法：从系统字体目录找一个中文字体（msyh.ttc / simhei.ttf / simsun.ttc / PingFang / Noto），
**只把用到的字形子集化嵌入** PDF（Type0 + CIDFontType2 + Identity-H），因此
- 不依赖阅读器自带中文字体（不会出现空白或方框）；
- 不需要 LaTeX / 第三方库。

排版：A4、中文段首缩进两格、行距 1.6、自动换行（中英混排、避头尾标点），
`# 标题` 行按居中加粗大字排版。
"""

from __future__ import annotations

import os
import struct
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 字体定位

CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\msyhl.ttc", r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\simkai.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def find_cjk_font(explicit: Optional[str] = None) -> str:
    """返回一个可用的中文 TrueType 字体路径；找不到则抛错（附排查提示）。"""
    if explicit:
        if os.path.exists(explicit):
            return explicit
        raise FileNotFoundError("指定的字体不存在：%s" % explicit)
    for p in CJK_FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    # 兜底：扫描常见字体目录里疑似中文字体的文件
    for d in (r"C:\Windows\Fonts", "/usr/share/fonts", "/System/Library/Fonts"):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            low = name.lower()
            if low.endswith((".ttf", ".ttc")) and ("yahei" in low or "hei" in low
                                                   or "song" in low or "noto" in low
                                                   or "cjk" in low or "pingfang" in low):
                return os.path.join(d, name)
    raise FileNotFoundError("未找到中文字体：可用 --font 指定，如 C:\\Windows\\Fonts\\msyh.ttc")


# ---------------------------------------------------------------- TrueType 解析

class TrueType:
    """最小可用的 TrueType 读取（含 TTC 取首个字体）。"""

    def __init__(self, path: str) -> None:
        with open(path, "rb") as f:
            data = f.read()
        self.data = data
        base = 0
        if data[:4] == b"ttcf":
            base = struct.unpack(">I", data[12:16])[0]
        self.base = base
        num_tables = struct.unpack(">H", data[base + 4:base + 6])[0]
        tables: Dict[bytes, Tuple[int, int]] = {}
        p = base + 12
        for _ in range(num_tables):
            tag = data[p:p + 4]
            off, length = struct.unpack(">II", data[p + 8:p + 16])
            tables[tag] = (off, length)
            p += 16
        self.tables = tables
        head = self.tab(b"head")
        self.units_per_em = struct.unpack(">H", head[18:20])[0]
        self.loc_format = struct.unpack(">h", head[50:52])[0]
        self.bbox = struct.unpack(">hhhh", head[36:44])
        maxp = self.tab(b"maxp")
        self.num_glyphs = struct.unpack(">H", maxp[4:6])[0]
        hhea = self.tab(b"hhea")
        self.num_hmetrics = struct.unpack(">H", hhea[34:36])[0]
        self.ascent, self.descent = struct.unpack(">hh", hhea[4:8])
        self.cmap = self._parse_cmap()
        self.loca = self._parse_loca()
        self.advances, self.lsbs = self._parse_hmtx()

    def tab(self, tag: bytes) -> bytes:
        off, length = self.tables[tag]
        return self.data[off:off + length]

    # ---- cmap ----
    def _parse_cmap(self) -> Dict[int, int]:
        cmap = self.tab(b"cmap")
        n = struct.unpack(">H", cmap[2:4])[0]
        best = None
        best_score = -1
        for i in range(n):
            pid, eid, off = struct.unpack(">HHI", cmap[4 + i * 8:12 + i * 8])
            fmt = struct.unpack(">H", cmap[off:off + 2])[0]
            if fmt not in (4, 12):
                continue
            score = {(3, 10): 5, (0, 4): 4, (3, 1): 3, (0, 3): 3, (0, 2): 3, (0, 1): 2}.get((pid, eid), 1)
            if fmt == 12 and score < 4:
                score = 3
            if score > best_score:
                best, best_score = (off, fmt), score
        mapping: Dict[int, int] = {}
        if not best:
            return mapping
        off, fmt = best
        if fmt == 4:
            seg_x2 = struct.unpack(">H", cmap[off + 6:off + 8])[0]
            seg = seg_x2 // 2
            ends = struct.unpack(">%dH" % seg, cmap[off + 14:off + 14 + seg_x2])
            starts = struct.unpack(">%dH" % seg, cmap[off + 16 + seg_x2:off + 16 + seg_x2 * 2])
            deltas = struct.unpack(">%dh" % seg, cmap[off + 16 + seg_x2 * 2:off + 16 + seg_x2 * 3])
            range_off_pos = off + 16 + seg_x2 * 3
            ranges = struct.unpack(">%dH" % seg, cmap[range_off_pos:range_off_pos + seg_x2])
            for i in range(seg):
                if starts[i] == 0xFFFF:
                    continue
                for c in range(starts[i], ends[i] + 1):
                    if ranges[i] == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        addr = range_off_pos + i * 2 + ranges[i] + (c - starts[i]) * 2
                        if addr + 2 > len(cmap):
                            continue
                        g = struct.unpack(">H", cmap[addr:addr + 2])[0]
                        if g:
                            g = (g + deltas[i]) & 0xFFFF
                    if g:
                        mapping[c] = g
        else:  # format 12
            ngroups = struct.unpack(">I", cmap[off + 12:off + 16])[0]
            p = off + 16
            for _ in range(ngroups):
                s, e, g = struct.unpack(">III", cmap[p:p + 12])
                for c in range(s, e + 1):
                    mapping[c] = g + (c - s)
                p += 12
        return mapping

    # ---- loca / hmtx ----
    def _parse_loca(self) -> List[int]:
        loca = self.tab(b"loca")
        out: List[int] = []
        if self.loc_format == 0:
            for i in range(self.num_glyphs + 1):
                out.append(struct.unpack(">H", loca[i * 2:i * 2 + 2])[0] * 2)
        else:
            for i in range(self.num_glyphs + 1):
                out.append(struct.unpack(">I", loca[i * 4:i * 4 + 4])[0])
        return out

    def _parse_hmtx(self) -> Tuple[List[int], List[int]]:
        hmtx = self.tab(b"hmtx")
        adv: List[int] = []
        lsb: List[int] = []
        last_a = 0
        for g in range(self.num_glyphs):
            if g < self.num_hmetrics:
                a, l = struct.unpack(">Hh", hmtx[g * 4:g * 4 + 4])
                last_a = a
            else:
                pos = self.num_hmetrics * 4 + (g - self.num_hmetrics) * 2
                a, l = last_a, struct.unpack(">h", hmtx[pos:pos + 2])[0]
            adv.append(a)
            lsb.append(l)
        return adv, lsb

    # ---- 字形 ----
    def glyph(self, gid: int) -> bytes:
        if gid < 0 or gid + 1 >= len(self.loca):
            return b""
        glyf = self.tab(b"glyf")
        return glyf[self.loca[gid]:self.loca[gid + 1]]

    def composite_components(self, data: bytes) -> List[int]:
        """返回复合字形引用的组件 gid 列表。"""
        if len(data) < 10:
            return []
        ncont = struct.unpack(">h", data[:2])[0]
        if ncont >= 0:
            return []
        comps: List[int] = []
        p = 10
        while p + 4 <= len(data):
            flags, comp = struct.unpack(">HH", data[p:p + 4])
            comps.append(comp)
            p += 4
            p += 4 if (flags & 0x0001) else 2
            if flags & 0x0008:
                p += 2
            elif flags & 0x0040:
                p += 4
            elif flags & 0x0080:
                p += 8
            if not (flags & 0x0020):
                break
        return comps

    def remap_composite(self, data: bytes, gid_map: Dict[int, int]) -> bytes:
        if len(data) < 10:          # 空字形（如空格）或无轮廓字形：原样返回
            return data
        ncont = struct.unpack(">h", data[:2])[0]
        if ncont >= 0:
            return data
        out = bytearray(data)
        p = 10
        while p + 4 <= len(out):
            flags, comp = struct.unpack(">HH", bytes(out[p:p + 4]))
            out[p + 2:p + 4] = struct.pack(">H", gid_map.get(comp, 0))
            p += 4
            p += 4 if (flags & 0x0001) else 2
            if flags & 0x0008:
                p += 2
            elif flags & 0x0040:
                p += 4
            elif flags & 0x0080:
                p += 8
            if not (flags & 0x0020):
                break
        return bytes(out)


# ---------------------------------------------------------------- 子集化

def _checksum(data: bytes) -> int:
    pad = (-len(data)) % 4
    data = data + b"\0" * pad
    s = 0
    for i in range(0, len(data), 4):
        s = (s + struct.unpack(">I", data[i:i + 4])[0]) & 0xFFFFFFFF
    return s


def _build_sfnt(tables: Dict[bytes, bytes], units_per_em: int) -> bytes:
    tags = sorted(tables)
    n = len(tags)
    search = 1
    entry = 0
    while search * 2 <= n:
        search *= 2
        entry += 1
    search *= 16
    entry = entry * 16 if n else 0
    range_shift = n * 16 - search

    header = struct.pack(">IHHHH", 0x00010000, n, search, entry, range_shift)
    offset = 12 + n * 16
    dir_parts = []
    body = []
    for tag in tags:
        data = tables[tag]
        padded = data + b"\0" * ((-len(data)) % 4)
        dir_parts.append(struct.pack(">4sIII", tag, _checksum(data), offset, len(data)))
        body.append(padded)
        offset += len(padded)
    sfnt = header + b"".join(dir_parts) + b"".join(body)

    # head.checkSumAdjustment
    head_off = None
    off = 12
    for i, tag in enumerate(tags):
        if tag == b"head":
            head_off = struct.unpack(">I", sfnt[12 + i * 16 + 8:12 + i * 16 + 12])[0]
            break
    if head_off is not None:
        adj = (0xB1B0AFBA - _checksum(sfnt)) & 0xFFFFFFFF
        sfnt = sfnt[:head_off + 8] + struct.pack(">I", adj) + sfnt[head_off + 12:]
    return sfnt


def subset_font(font: TrueType, codepoints: Sequence[int]) -> Tuple[bytes, Dict[int, int], Dict[int, int]]:
    """把用到的字形子集化。返回 (sfnt 字节, 码点→新gid, 新gid→advance)。"""
    used: Dict[int, int] = {}          # 旧 gid → 该 gid 对应的码点（代表）
    for cp in codepoints:
        gid = font.cmap.get(cp)
        if gid and gid not in used:
            used[gid] = cp

    # 复合字形的组件闭包
    queue = list(used)
    while queue:
        g = queue.pop()
        for comp in font.composite_components(font.glyph(g)):
            if comp not in used and comp < font.num_glyphs:
                used[comp] = used.get(g, 0)
                queue.append(comp)

    old_gids = [0] + sorted(g for g in used if g != 0)
    gid_map = {old: new for new, old in enumerate(old_gids)}

    glyf = bytearray()
    loca = [0]
    for old in old_gids:
        data = font.remap_composite(font.glyph(old), gid_map) if old else b""
        data += b"\0" * ((-len(data)) % 4)
        glyf += data
        loca.append(len(glyf))

    # cmap（format 12：按码点分组，保证文本可提取）
    groups = bytearray()
    ngroups = 0
    items = sorted((cp, gid_map[g]) for g, cp in used.items() if g in gid_map and cp)
    i = 0
    while i < len(items):
        s_cp, s_gid = items[i]
        j = i
        while (j + 1 < len(items) and items[j + 1][0] == items[j][0] + 1
               and items[j + 1][1] == items[j][1] + 1):
            j += 1
        e_cp, _ = items[j]
        groups += struct.pack(">III", s_cp, e_cp, s_gid)
        ngroups += 1
        i = j + 1
    fmt12 = struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, ngroups) + bytes(groups)
    # 另附一个最小 format 4（部分解析器要求存在）：单段 0xFFFF → gid 0
    fmt4 = (struct.pack(">7H", 4, 32, 0, 4, 2, 1, 0)
            + struct.pack(">2H", 0xFFFF, 0xFFFF)      # endCode
            + b"\0\0"                                  # reservedPad
            + struct.pack(">2H", 0xFFFF, 0xFFFF)       # startCode
            + struct.pack(">2h", 1, 1)                 # idDelta
            + struct.pack(">2H", 0, 0))                # idRangeOffset
    first = 4 + 8 * 2                                  # 表头 4 + 两条编码记录
    cmap = (struct.pack(">HH", 0, 2)
            + struct.pack(">HHI", 0, 2, first)
            + struct.pack(">HHI", 3, 10, first + len(fmt4))
            + fmt4 + fmt12)

    n = len(old_gids)
    hmtx = bytearray()
    for new, old in enumerate(old_gids):
        hmtx += struct.pack(">Hh", font.advances[old], font.lsbs[old])
    hhea = bytearray(font.tab(b"hhea"))
    hhea[34:36] = struct.pack(">H", n)
    head = bytearray(font.tab(b"head"))
    head[50:52] = struct.pack(">h", 1)      # long loca
    head[8:12] = struct.pack(">I", 0)       # 稍后重算
    maxp = bytearray(font.tab(b"maxp"))
    maxp[4:6] = struct.pack(">H", n)

    tables: Dict[bytes, bytes] = {
        b"head": bytes(head),
        b"hhea": bytes(hhea),
        b"maxp": bytes(maxp),
        b"hmtx": bytes(hmtx),
        b"cmap": cmap,
        b"glyf": bytes(glyf),
        b"loca": b"".join(struct.pack(">I", x) for x in loca),
    }
    for tag in (b"OS/2", b"name", b"post", b"cvt ", b"fpgm", b"prep", b"gasp"):
        if tag in font.tables:
            tables[tag] = font.tab(tag)

    sfnt = _build_sfnt(tables, font.units_per_em)
    advances = {gid_map[old]: font.advances[old] for old in old_gids}
    return sfnt, {cp: gid_map[g] for g, cp in used.items() if g in gid_map and cp}, advances


# ---------------------------------------------------------------- PDF 写入

A4_W, A4_H = 595.276, 841.89
HEAD_START = "，。！？；：、）》」』”’％%…—"          # 不得出现在行首
HEAD_END = "（《「『“‘"                                # 不得出现在行尾


class _Pdf:
    def __init__(self) -> None:
        self.objects: List[bytes] = []

    def add(self, body: bytes) -> int:
        self.objects.append(body)
        return len(self.objects)

    def out(self) -> bytes:
        buf = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(self.objects, 1):
            offsets.append(len(buf))
            buf += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(buf)
        buf += b"xref\n0 %d\n" % (len(self.objects) + 1)
        buf += b"0000000000 65535 f \n"
        for off in offsets:
            buf += b"%010d 00000 n \n" % off
        buf += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(self.objects) + 1, xref))
        return bytes(buf)


def _esc_name(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s)[:40] or "Embedded"


def _utf16be_hex(cp: int) -> bytes:
    if cp > 0xFFFF:
        v = cp - 0x10000
        return b"%04X%04X" % (0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF))
    return b"%04X" % cp


def _tounicode_cmap(codepoint_to_gid: Dict[int, int]) -> bytes:
    """生成 ToUnicode CMap（gid → Unicode），使 PDF 文字可复制、可被校验。"""
    gid_to_cp: Dict[int, int] = {}
    for cp, gid in codepoint_to_gid.items():
        gid_to_cp.setdefault(gid, cp)
    items = sorted(gid_to_cp.items())
    parts = [
        b"/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        b"/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n",
    ]
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        parts.append(b"%d beginbfchar\n" % len(chunk))
        for gid, cp in chunk:
            parts.append(b"<%04X> <%s>\n" % (gid, _utf16be_hex(cp)))
        parts.append(b"endbfchar\n")
    parts.append(b"endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n")
    return b"".join(parts)


def extract_text(path: str) -> str:
    """从本模块生成的 PDF 中回读文字（校验字形编码链路是否自洽）。"""
    import re as _re

    with open(path, "rb") as f:
        data = f.read()
    gid_to_cp: Dict[int, str] = {}
    lines: List[str] = []
    for m in _re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"\nendstream", start)
        if end < 0:
            continue
        blob = data[start:end]
        if b"beginbfchar" in blob:
            for bm in _re.finditer(rb"<([0-9A-Fa-f]{4})>\s*<([0-9A-Fa-f]{4,8})>", blob):
                gid = int(bm.group(1), 16)
                hx = bm.group(2).decode("ascii")
                try:
                    gid_to_cp[gid] = bytes.fromhex(hx).decode("utf-16-be")
                except Exception:  # noqa: BLE001
                    continue
        elif b"Tj" in blob:
            cur = []
            for hm in _re.finditer(rb"<([0-9A-Fa-f]+)>\s*Tj", blob):
                hx = hm.group(1).decode("ascii")
                cur.append("".join(gid_to_cp.get(int(hx[i:i + 4], 16), "")
                                   for i in range(0, len(hx) - 3, 4)))
            if cur:
                lines.append("".join(cur))
    return "\n".join(lines)


def _wrap(paras: List[str], fs: float, width: float, advances: Dict[int, int],
          cmap: Dict[int, int], units: int) -> List[Tuple[str, float, str]]:
    """返回 [(type, size, text)]；type ∈ {h1, p}。按字符宽度换行并处理避头尾。"""
    lines: List[Tuple[str, float, str]] = []
    for kind, text in paras:
        if kind == "h1":
            lines.append(("h1", fs + 3.5, text))
            lines.append(("gap", fs, ""))
            continue
        indent = "\u3000\u3000"
        cur = indent
        cur_w = _text_width(indent, fs, advances, cmap, units)
        for ch in text:
            w = _text_width(ch, fs, advances, cmap, units)
            if cur_w + w > width and len(cur) > len(indent):
                if ch in HEAD_START and cur:
                    cur += ch                      # 避头：标点跟随上一行
                    lines.append(("p", fs, cur))
                    cur, cur_w = "", 0.0
                    continue
                if cur and cur[-1] in HEAD_END:     # 避尾：开引号带到下一行
                    cur = cur[:-1]
                    lines.append(("p", fs, cur))
                    cur, cur_w = ch, w
                    continue
                lines.append(("p", fs, cur))
                cur, cur_w = "", 0.0
            cur += ch
            cur_w += w
        if cur:
            lines.append(("p", fs, cur))
    return lines


def _text_width(s: str, fs: float, advances: Dict[int, int], cmap: Dict[int, int],
                units: int) -> float:
    total = 0
    for ch in s:
        gid = cmap.get(ord(ch), 0)
        adv = advances.get(gid, advances.get(0, units // 2))
        total += adv * fs / units
    return total


def export_pdf(output_path: str, title: str, author: str, description: str,
               chapters: Sequence[Tuple[str, str]], font_path: Optional[str] = None,
               font_size: float = 10.5) -> str:
    """导出 A4 中文 PDF（无 TeX 依赖）。chapters 为 [(章节标题, 正文文本)]。"""
    path = find_cjk_font(font_path)
    font = TrueType(path)

    # 收集文本
    paras: List[Tuple[str, str]] = []
    for ctitle, ctext in chapters:
        if ctitle:
            paras.append(("h1", ctitle.strip()))
        for raw in ctext.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                paras.append(("h1", line.lstrip("#").strip()))
            else:
                paras.append(("p", line))
    head_paras: List[Tuple[str, str]] = [("h1", title), ("p", author)]
    if description:
        head_paras += [("h1", "简介"), ("p", description.strip())]

    all_text = "".join(t for _, t in head_paras + paras)
    codepoints = sorted({ord(ch) for ch in all_text})
    sfnt, cmap, advances = subset_font(font, codepoints)

    lines = _wrap(head_paras, font_size, A4_W - 130, advances, cmap, font.units_per_em)
    lines += _wrap(paras, font_size, A4_W - 130, advances, cmap, font.units_per_em)

    # 分页 + 内容流
    leading = font_size * 1.62
    top, bottom, left = A4_H - 76, 68, 65
    y = top
    streams: List[bytes] = []
    cur = bytearray(b"BT\n")

    def new_page() -> None:
        nonlocal cur, y
        cur += b"ET"
        streams.append(bytes(cur))
        cur = bytearray(b"BT\n")
        y = top

    for kind, size, text in lines:
        if kind == "gap":
            y -= size * 0.6
            continue
        if y - leading < bottom:
            new_page()
        if kind == "h1":
            w = _text_width(text, size, advances, cmap, font.units_per_em)
            x = max(left, (A4_W - w) / 2)
            y -= leading * 1.5
            cur += b"/F1 %.2f Tf %.2f TL %.2f %.2f Td <" % (size, size * 1.62, x, y)
            y -= size * 1.62
        else:
            cur += b"/F1 %.2f Tf %.2f TL %.2f %.2f Td <" % (size, leading, left, y)
            y -= leading
        for ch in text:
            cur += b"%04X" % cmap.get(ord(ch), 0)
        cur += b"> Tj\n"
    cur += b"ET"
    streams.append(bytes(cur))
    if not streams:
        streams = [b"BT ET"]

    # ---- 固定对象编号：1=Catalog 2=Pages 3=FontFile2 4=Descriptor 5=CIDFont 6=Type0 ----
    #      7..7+P-1 = 页对象；7+P..7+2P-1 = 内容流
    n_pages = len(streams)
    subset_tag = _esc_name(os.path.splitext(os.path.basename(path))[0])
    fontfile = (b"<< /Length %d /Length1 %d >>\nstream\n" % (len(sfnt), len(sfnt))
                + sfnt + b"\nendstream")
    w_parts = [b"%d [%d]" % (gid, round(advances[gid] * 1000 / font.units_per_em))
               for gid in sorted(advances)]
    descriptor = (
        b"<< /Type /FontDescriptor /FontName /%s+%s /Flags 4 /FontBBox [%d %d %d %d] "
        b"/ItalicAngle 0 /Ascent %d /Descent %d /CapHeight %d /StemV 80 /FontFile2 3 0 R >>"
        % (subset_tag.encode(), subset_tag.encode(), font.bbox[0], font.bbox[1],
           font.bbox[2], font.bbox[3], font.ascent, abs(font.descent), font.ascent))
    cidfont = (
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s+%s "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        b"/FontDescriptor 4 0 R /W [%s] /CIDToGIDMap /Identity >>"
        % (subset_tag.encode(), subset_tag.encode(), b" ".join(w_parts)))
    tounicode_body = _tounicode_cmap(cmap)
    type0 = (b"<< /Type /Font /Subtype /Type0 /BaseFont /%s+%s /Encoding /Identity-H "
             b"/DescendantFonts [5 0 R] /ToUnicode 7 0 R >>"
             % (subset_tag.encode(), subset_tag.encode()))
    tounicode = (b"<< /Length %d >>\nstream\n" % len(tounicode_body)
                 + tounicode_body + b"\nendstream")

    # 7 = ToUnicode CMap（文字可复制/可抽取）
    #  8..8+P-1 = 页对象；8+P..8+2P-1 = 内容流
    page_ids = [8 + i for i in range(n_pages)]
    content_ids = [8 + n_pages + i for i in range(n_pages)]
    media = b"[0 0 %.2f %.2f]" % (A4_W, A4_H)
    resources = b"<< /Font << /F1 6 0 R >> >>"
    pages_node = (b"<< /Type /Pages /Count %d /Kids [%s] >>"
                  % (n_pages, b" ".join(b"%d 0 R" % i for i in page_ids)))

    objs: List[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", pages_node,
                         fontfile, descriptor, cidfont, type0, tounicode]
    for i in range(n_pages):
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox " + media
                    + b" /Resources " + resources
                    + b" /Contents %d 0 R >>" % content_ids[i])
    for s in streams:
        objs.append(b"<< /Length %d >>\nstream\n" % len(s) + s + b"\nendstream")

    pdf = _Pdf()
    pdf.objects = objs
    data = pdf.out()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(data)
    return output_path
