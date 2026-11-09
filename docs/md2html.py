"""
docs/md2html.py — dựng bản HTML in được từ một file .md, thay pandoc khi máy không có.

    python docs/md2html.py <file.md> <ra.html> <tieu_de> <file.css>

Chỉ thư viện chuẩn. `docs/dung-ban-in.ps1` gọi file này khi không tìm thấy pandoc.

VÌ SAO NẰM TRONG REPO
---------------------
Bản đầu (10/2026) nằm ở thư mục tạm của một phiên làm việc, và mất khi thư mục đó
bị dọn — đúng lúc tài liệu vừa dời vào docs/chu-ky-01/ và cần dựng lại bản in.
Công cụ dựng tài liệu cũng là mã của dự án.

Phủ đúng phần GFM mà tài liệu ANSER dùng: tiêu đề (id kiểu GFM + mục lục nav#TOC
độ sâu 3), đoạn, bảng, khối code có rào, trích dẫn lồng, danh sách lồng (kể cả
bảng nằm trong một mục danh sách), hình (nhúng base64, đường dẫn tương đối theo
thư mục của file .md — như `--embed-resources --resource-path`), code / đậm /
nghiêng / gạch / liên kết trong dòng, đường kẻ ngang. Không phủ: HTML thô, chú
thích cuối trang, danh sách việc `- [ ]` (in ra nguyên văn).
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
import sys
from pathlib import Path

THU_MUC_MD = Path(".")


# ------------------------------------------------------------------ trong dòng

def _img(src: str, alt: str) -> str:
    duong = (THU_MUC_MD / src).resolve()
    if duong.is_file():
        loai = mimetypes.guess_type(duong.name)[0] or "application/octet-stream"
        if duong.suffix.lower() == ".svg":
            loai = "image/svg+xml"
        src = f"data:{loai};base64," + base64.b64encode(duong.read_bytes()).decode()
    return f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" />'


def trong_dong(s: str) -> str:
    giu: list[str] = []

    def cat(x: str) -> str:
        giu.append(x)
        return f"\x00{len(giu) - 1}\x00"

    # code trước tiên: bên trong code không xử lý gì khác
    s = re.sub(r"(`+)(.+?)\1",
               lambda m: cat(f"<code>{html.escape(m.group(2).strip())}</code>"), s)
    s = html.escape(s, quote=False)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: cat(_img(m.group(2), m.group(1))), s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: cat(f'<a href="{html.escape(m.group(2))}">') + m.group(1) + cat("</a>"), s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s)
    s = re.sub(r"\\([|*_`\[\]#\\])", r"\1", s)
    while "\x00" in s:
        s = re.sub(r"\x00(\d+)\x00", lambda m: giu[int(m.group(1))], s)
    return s


# ------------------------------------------------------------------ tiêu đề

_ID_DA_DUNG: dict[str, int] = {}
MUC_LUC: list[tuple[int, str, str]] = []


def _id_gfm(chu: str) -> str:
    """Id kiểu GitHub: chữ thường, bỏ dấu câu (giữ chữ có dấu), cách -> '-'."""
    tho = re.sub(r"<[^>]+>", "", chu)
    tho = html.unescape(tho).lower()
    tho = re.sub(r"[^\w\- ]", "", tho)
    goc = tho.replace(" ", "-")
    n = _ID_DA_DUNG.get(goc, 0)
    _ID_DA_DUNG[goc] = n + 1
    return goc if n == 0 else f"{goc}-{n}"


# ------------------------------------------------------------------ khối

_RAO = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
_TIEU_DE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_KE_NGANG = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_MUC_DS = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_DONG_BANG_KE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _o_bang(dong: str) -> list[str]:
    d = dong.strip()
    if d.startswith("|"):
        d = d[1:]
    if d.endswith("|") and not d.endswith("\\|"):
        d = d[:-1]
    o, cur, trong_code = [], "", False
    i = 0
    while i < len(d):
        c = d[i]
        if c == "\\" and i + 1 < len(d) and d[i + 1] == "|":
            cur += "\\|"
            i += 2
            continue
        if c == "`":
            trong_code = not trong_code
        if c == "|" and not trong_code:
            o.append(cur.strip())
            cur = ""
        else:
            cur += c
        i += 1
    o.append(cur.strip())
    return o


def _bang(dong: list[str]) -> str:
    dau = _o_bang(dong[0])
    ra = ["<table>", "<thead>", "<tr>"]
    ra += [f"<th>{trong_dong(o.replace(chr(92) + '|', '|'))}</th>" for o in dau]
    ra += ["</tr>", "</thead>", "<tbody>"]
    for d in dong[2:]:
        ra.append("<tr>")
        ra += [f"<td>{trong_dong(o.replace(chr(92) + '|', '|'))}</td>" for o in _o_bang(d)]
        ra.append("</tr>")
    ra += ["</tbody>", "</table>"]
    return "\n".join(ra)


def _thut(d: str) -> int:
    return len(d) - len(d.lstrip(" "))


def _la_bat_dau_khoi(d: str) -> bool:
    return bool(_TIEU_DE.match(d) or _RAO.match(d) or _KE_NGANG.match(d)
                or d.lstrip().startswith(">") or _MUC_DS.match(d)
                or d.lstrip().startswith("|"))


def khoi(dong: list[str]) -> str:
    ra: list[str] = []
    i = 0
    while i < len(dong):
        d = dong[i]
        if not d.strip():
            i += 1
            continue

        m = _RAO.match(d)
        if m:
            rao, thut = m.group(2), len(m.group(1))
            ngon_ngu = m.group(3).strip()
            noi_dung = []
            i += 1
            while i < len(dong) and not dong[i].strip().startswith(rao):
                noi_dung.append(dong[i][thut:] if dong[i][:thut].strip() == "" else dong[i])
                i += 1
            i += 1
            lop = f' class="language-{html.escape(ngon_ngu)}"' if ngon_ngu else ""
            ra.append(f"<pre><code{lop}>{html.escape(chr(10).join(noi_dung))}</code></pre>")
            continue

        m = _TIEU_DE.match(d)
        if m:
            cap = len(m.group(1))
            chu = trong_dong(m.group(2))
            ma = _id_gfm(chu)
            if cap <= 3:
                MUC_LUC.append((cap, ma, chu))
            ra.append(f'<h{cap} id="{ma}">{chu}</h{cap}>')
            i += 1
            continue

        if _KE_NGANG.match(d):
            ra.append("<hr />")
            i += 1
            continue

        if d.lstrip().startswith(">"):
            trich = []
            while i < len(dong) and dong[i].lstrip().startswith(">"):
                trich.append(re.sub(r"^\s*>\s?", "", dong[i]))
                i += 1
            ra.append(f"<blockquote>\n{khoi(trich)}\n</blockquote>")
            continue

        if d.lstrip().startswith("|") and i + 1 < len(dong) and _DONG_BANG_KE.match(dong[i + 1]):
            bang = [d, dong[i + 1]]
            i += 2
            while i < len(dong) and dong[i].lstrip().startswith("|"):
                bang.append(dong[i])
                i += 1
            ra.append(_bang(bang))
            continue

        m = _MUC_DS.match(d)
        if m:
            goc = len(m.group(1))
            co_so = m.group(2)[0].isdigit()
            the = "ol" if co_so else "ul"
            muc: list[list[str]] = []
            while i < len(dong):
                dd = dong[i]
                mm = _MUC_DS.match(dd)
                if mm and len(mm.group(1)) == goc and mm.group(2)[0].isdigit() == co_so:
                    thut_noi = len(mm.group(1)) + len(mm.group(2)) + 1
                    muc.append([" " * thut_noi + mm.group(3)])
                    i += 1
                    continue
                if not dd.strip():
                    # dòng trống: còn trong danh sách nếu dòng sau thụt vào hoặc là mục cùng cấp
                    j = i + 1
                    while j < len(dong) and not dong[j].strip():
                        j += 1
                    if j < len(dong) and (_thut(dong[j]) > goc or (
                            (m2 := _MUC_DS.match(dong[j])) and len(m2.group(1)) == goc)):
                        muc[-1].append("")
                        i += 1
                        continue
                    break
                if _thut(dd) > goc or not _la_bat_dau_khoi(dd):
                    muc[-1].append(dd)
                    i += 1
                    continue
                break
            phan = []
            for m_ in muc:
                thut_min = min((_thut(x) for x in m_ if x.strip()), default=0)
                noi = [x[thut_min:] if x.strip() else "" for x in m_]
                ben_trong = khoi(noi)
                # mục chỉ có một đoạn thì bỏ <p> cho gọn, giống pandoc với danh sách sát
                if ben_trong.count("<p>") == 1 and ben_trong.startswith("<p>") and "\n" not in ben_trong:
                    ben_trong = ben_trong[3:-4]
                phan.append(f"<li>{ben_trong}</li>")
            so_dau = re.match(r"\d+", m.group(2))
            mo = f'<{the} start="{int(so_dau.group())}">' if so_dau else f"<{the}>"
            ra.append(mo + "\n" + "\n".join(phan) + f"\n</{the}>")
            continue

        doan = [d.strip()]
        i += 1
        while i < len(dong) and dong[i].strip() and not _la_bat_dau_khoi(dong[i]):
            doan.append(dong[i].strip())
            i += 1
        ra.append(f"<p>{trong_dong(' '.join(doan))}</p>")
    return "\n".join(ra)


def _muc_luc() -> str:
    if not MUC_LUC:
        return ""
    ra = ['<nav id="TOC" role="doc-toc">', "<ul>"]
    cap_truoc = MUC_LUC[0][0]
    mo = 0
    for cap, ma, chu in MUC_LUC:
        while cap > cap_truoc:
            ra.append("<ul>")
            mo += 1
            cap_truoc += 1
        while cap < cap_truoc and mo:
            ra.append("</ul>")
            mo -= 1
            cap_truoc -= 1
        ra.append(f'<li><a href="#{ma}">{re.sub(r"<a [^>]*>|</a>", "", chu)}</a></li>')
    ra += ["</ul>"] * mo + ["</ul>", "</nav>"]
    return "\n".join(ra)


def main() -> None:
    global THU_MUC_MD
    if len(sys.argv) != 5:
        sys.exit("dùng: python docs/md2html.py <file.md> <ra.html> <tieu_de> <file.css>")
    md, ra, tieu_de, css = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    THU_MUC_MD = md.parent
    than = khoi(md.read_text(encoding="utf-8").splitlines())
    trang = (
        '<!DOCTYPE html>\n<html lang="vi">\n<head>\n<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>{html.escape(tieu_de)}</title>\n<style>\n{css.read_text(encoding='utf-8')}\n</style>\n"
        f"</head>\n<body>\n{_muc_luc()}\n{than}\n</body>\n</html>\n"
    )
    ra.write_text(trang, encoding="utf-8")


if __name__ == "__main__":
    main()
