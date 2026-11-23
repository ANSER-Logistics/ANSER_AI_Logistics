"""
offline_training/chay_bong.py — chế độ bóng: chạy Brain trên tệp Excel, KHÔNG cho ai thấy kết quả, chỉ ghi lại để người đọc xem (A6, brain#324; việc A27 / #208 chỉ còn là chạy).

VÌ SAO CÓ
---------
Trước khi cho khách thấy một câu trả lời của Brain phải đo lỗi thật: bao nhiêu phát hiện đúng, bao nhiêu báo oan, có con số nào sai mà không gắn nhãn "chưa kiểm", có dữ liệu khách này lọt sang khách kia
không. Công cụ này gọi ĐÚNG các route `/tools/*-import` mà Body sẽ gọi, trên một thư mục tệp, rồi ghi mỗi phát hiện thành một "ca" để người đọc lại.

NHẬT KÝ KHÔNG CHỨA NỘI DUNG (R2)
--------------------------------
`ca.jsonl` và `phieu_doc.csv` chỉ chứa mã băm, tên loại, mức độ và cờ đúng/sai: không tên hàng, không mã hàng, không số tiền, không tên khách. Người đọc cần nội dung của một ca thì chạy `--tra-cuu`
trên MÁY CỦA HỌ, nơi tệp gốc đang nằm: nội dung chỉ ra màn hình, không vào tệp nào.

BỐN KIỂM TỰ ĐỘNG TRÊN MỖI TỆP (tên bất biến, không phải lỗi nghiệp vụ)
-------------------------------------------------------------------
- `doc_hong_nhung_co_audit`   đọc hỏng mà vẫn có kết quả kiểm hoặc giá vốn suy ra: số suy từ bảng đọc lệch cột nhìn rất thuyết phục (R1).
- `thieu_truong_phat_hien`    một phát hiện thiếu tiêu đề, bằng chứng, gợi ý, hoặc mức độ ngoài danh sách.
- `tien_khong_huu_han`        `money_impact` là NaN, vô cực, hoặc không phải số (`None` hợp lệ: "chưa quy ra tiền được").
- `khong_tat_dinh`            chạy hai lần cùng một tệp ra hai kết quả khác nhau.
- `ro_cheo_tep`               phát hiện của tệp này nhắc tới mã hàng/đối tác chỉ có ở tệp khác (rò chéo khách).
Mọi vi phạm in ra và làm mã thoát 1. Nhãn "chưa kiểm" của kết quả thì người đọc soát bằng phiếu (cột `ket_luan`).

GIỚI HẠN: công cụ đo được "kết quả có tự nhất quán và có kèm nhãn không". NÓ KHÔNG BIẾT phát hiện nào đúng nghiệp vụ: đó là việc của người đọc phiếu (kế toán thật là tốt nhất).

CHẠY
----
    py -m offline_training.chay_bong --sinh-hu-cau 12 --ra ket_qua_bong          # dữ liệu hư cấu, đủ ≥ 100 ca
    py -m offline_training.chay_bong --thu-muc THU_MUC_TEP --ra ket_qua_bong       # tệp khách tự tải
    py -m offline_training.chay_bong --tong-hop ket_qua_bong [--doi-du-nguoi-doc]  # bảng tổng hợp; thoát 1 nếu còn ca chưa đọc
    py -m offline_training.chay_bong --tra-cuu CA_ID --thu-muc THU_MUC_TEP         # xem nội dung một ca (chỉ ra màn hình)
Chạy trong tiến trình (`ENV=LOCAL`, không GPU) hoặc vào một Brain đang chạy: `--url http://127.0.0.1:8000`; có `API_AUTH_TOKEN` trong môi trường thì gửi kèm.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from src.core.findings import MUC_DO
from src.core.utils import bo_dau

# Tên tệp -> route. Khớp theo chữ không dấu trong TÊN TỆP; không khớp thì bỏ qua và nói rõ.
LOAI_TEP = (
    ("/tools/inventory-import", ("ton kho", "ton_kho", "nxt", "nhap xuat ton"), "lines"),
    ("/tools/partner-import", ("khach hang", "khach_hang", "nha cung cap", "nha_cung_cap", "ncc", "doi tac"), "partners"),
    ("/tools/product-import", ("hang hoa", "hang_hoa", "danh muc", "san pham"), "products"),
)

BAT_BIEN = (
    "doc_hong_nhung_co_audit", "thieu_truong_phat_hien", "tien_khong_huu_han", "khong_tat_dinh", "ro_cheo_tep",
)
KET_LUAN_HOP_LE = ("dung", "oan", "thieu")      # đúng; báo oan; Brain bỏ sót (người đọc thấy lỗi mà Brain không báo)
COT_PHIEU = ["ca", "tep", "tool", "kind", "muc", "nguoi_doc", "ket_luan", "ghi_chu"]


# ---------------------------------------------------------------------------
# Hàm thuần: băm, nhận dạng, kiểm bất biến
# ---------------------------------------------------------------------------

def bam(*phan: Any, dai: int = 12) -> str:
    return hashlib.sha256("|".join(str(p) for p in phan).encode("utf-8")).hexdigest()[:dai]


def loai_cua_tep(ten: str) -> Optional[tuple[str, str]]:
    """(route, khoá danh sách bản ghi trong `import`) theo tên tệp; None = không nhận ra."""
    s = bo_dau(Path(ten).stem)
    for route, mau, khoa in LOAI_TEP:
        if any(m in s for m in mau):
            return route, khoa
    return None


def _ma_cua(payload: dict, khoa: str) -> set[str]:
    return {str(b.get("code")) for b in (payload.get("import") or {}).get(khoa) or [] if b.get("code")}


def _phat_hien_cua(payload: dict) -> list[dict]:
    return list((payload.get("audit") or {}).get("findings") or [])


def kiem_bat_bien(payload: dict, payload_lan_hai: Optional[dict], khoa_ban_ghi: str, ma_tep_khac: set[str]) -> list[str]:
    """Danh sách tên bất biến bị vi phạm (không lặp). Rỗng = sạch."""
    vi_pham: list[str] = []
    imp = payload.get("import") or {}
    if not imp.get("ok") and (payload.get("audit") is not None or payload.get("unit_costs")):
        vi_pham.append("doc_hong_nhung_co_audit")
    ma_tep = _ma_cua(payload, khoa_ban_ghi)
    for f in _phat_hien_cua(payload):
        if not (f.get("title") and f.get("evidence") and f.get("suggestion") and f.get("severity") in MUC_DO):
            vi_pham.append("thieu_truong_phat_hien")
        tien = f.get("money_impact")
        if tien is not None and (isinstance(tien, bool) or not isinstance(tien, (int, float)) or not math.isfinite(tien)):
            vi_pham.append("tien_khong_huu_han")
        if f.get("code") and str(f["code"]) in ma_tep_khac and str(f["code"]) not in ma_tep:
            vi_pham.append("ro_cheo_tep")
    if payload_lan_hai is not None and json.dumps(payload, sort_keys=True, default=str) != json.dumps(payload_lan_hai, sort_keys=True, default=str):
        vi_pham.append("khong_tat_dinh")
    return [v for v in BAT_BIEN if v in vi_pham]


def dong_ca(tep: str, route: str, f: dict, thu_tu: int) -> dict:
    """Một dòng `ca.jsonl` cho một phát hiện. CHỈ loại, mức độ, cờ và băm: không nội dung."""
    return {
        "loai_ban_ghi": "phat_hien",
        "ca": bam(tep, route, f.get("kind"), f.get("code"), thu_tu, dai=10),
        "tep": tep,
        "tool": route.rsplit("/", 1)[-1],
        "kind": f.get("kind"),
        "muc": f.get("severity"),
        "co_tien": f.get("money_impact") is not None,
        "co_bang_chung": bool(f.get("evidence")),
        "co_goi_y": bool(f.get("suggestion")),
    }


# ---------------------------------------------------------------------------
# Gọi route
# ---------------------------------------------------------------------------

class KetNoi:
    """Gọi `/tools/*-import`: trong tiến trình (mặc định) hoặc tới một Brain đang chạy (`--url`)."""

    def __init__(self, url: Optional[str] = None):
        self.token = os.getenv("API_AUTH_TOKEN") or None
        if url:
            import httpx
            self._c: Any = httpx.Client(base_url=url, timeout=120)
        else:
            from fastapi.testclient import TestClient

            from src.api.main import app
            self._c = TestClient(app)

    def goi(self, route: str, ten: str, du_lieu: bytes) -> tuple[int, dict]:
        head = {"X-Api-Token": self.token} if self.token else {}
        r = self._c.post(route, files={"file": (ten, du_lieu, "application/octet-stream")}, headers=head)
        try:
            return r.status_code, r.json() if r.status_code == 200 else {}
        except ValueError:
            return r.status_code, {}


def chay_mot_tep(kn: Any, duong: Path, ma_tep_khac: set[str]) -> tuple[list[dict], Optional[tuple[str, str, set[str]]]]:
    """Chạy một tệp hai lần. Trả (các dòng nhật ký, (tệp băm, route, tập mã của tệp) hoặc None nếu bỏ qua)."""
    loai = loai_cua_tep(duong.name)
    du_lieu = duong.read_bytes()
    tep = hashlib.sha256(du_lieu).hexdigest()[:12]
    if loai is None:
        return [{"loai_ban_ghi": "tep", "tep": tep, "tool": None, "bo_qua": "không nhận ra loại tệp theo tên"}], None
    route, khoa = loai
    t0 = time.perf_counter()
    ma, p1 = kn.goi(route, duong.name, du_lieu)
    ms = int((time.perf_counter() - t0) * 1000)
    _, p2 = kn.goi(route, duong.name, du_lieu) if ma == 200 else (0, None)
    vi_pham = kiem_bat_bien(p1, p2, khoa, ma_tep_khac) if ma == 200 else []
    if ma >= 500:
        vi_pham.append("loi_may_chu")
    imp = p1.get("import") or {}
    dong = [{
        "loai_ban_ghi": "tep", "tep": tep, "tool": route.rsplit("/", 1)[-1], "http": ma,
        "doc_duoc": bool(imp.get("ok")), "so_ban_ghi": imp.get("rows_parsed"),
        "so_phat_hien": len(_phat_hien_cua(p1)), "ms": ms, "vi_pham": vi_pham,
    }]
    dong += [dong_ca(tep, route, f, i) for i, f in enumerate(_phat_hien_cua(p1))]
    return dong, (tep, route, _ma_cua(p1, khoa)) if ma == 200 else None


def chay_thu_muc(kn: Any, thu_muc: Path) -> list[dict]:
    tep = sorted(p for p in thu_muc.iterdir() if p.suffix.lower() == ".xlsx")
    # Vòng một lấy tập mã của từng tệp để vòng hai kiểm rò chéo: mã chỉ có ở tệp KHÁC mà lọt vào phát hiện của tệp này.
    ma_moi_tep: dict[Path, set[str]] = {}
    for p in tep:
        loai = loai_cua_tep(p.name)
        if loai is None:
            continue
        ma, kq = kn.goi(loai[0], p.name, p.read_bytes())
        ma_moi_tep[p] = _ma_cua(kq, loai[1]) if ma == 200 else set()
    ra: list[dict] = []
    for p in tep:
        khac = set().union(*(m for q, m in ma_moi_tep.items() if q != p)) if len(ma_moi_tep) > 1 else set()
        dong, _ = chay_mot_tep(kn, p, khac)
        ra += dong
    return ra


# ---------------------------------------------------------------------------
# Ghi, phiếu đọc, tổng hợp
# ---------------------------------------------------------------------------

def ghi_ket_qua(dong: list[dict], ra: Path) -> None:
    ra.mkdir(parents=True, exist_ok=True)
    with open(ra / "ca.jsonl", "w", encoding="utf-8") as f:
        for d in dong:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(ra / "phieu_doc.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COT_PHIEU)
        for d in dong:
            if d["loai_ban_ghi"] == "phat_hien":
                w.writerow([d["ca"], d["tep"], d["tool"], d["kind"], d["muc"], "", "", ""])


def doc_ca(ra: Path) -> list[dict]:
    return [json.loads(x) for x in (ra / "ca.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def doc_phieu(ra: Path) -> list[dict]:
    with open(ra / "phieu_doc.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def tong_hop(ra: Path, doi_du_nguoi_doc: bool = False) -> tuple[str, int]:
    """(bảng chữ, mã thoát). Thoát 1 khi có vi phạm bất biến, hoặc `doi_du_nguoi_doc` mà còn ca chưa có kết luận hợp lệ."""
    dong = doc_ca(ra)
    tep = [d for d in dong if d["loai_ban_ghi"] == "tep"]
    ca = [d for d in dong if d["loai_ban_ghi"] == "phat_hien"]
    vi_pham = Counter(v for d in tep for v in d.get("vi_pham", []))
    phieu = doc_phieu(ra)
    da_doc = [p for p in phieu if (p.get("ket_luan") or "").strip().lower() in KET_LUAN_HOP_LE]
    ket_luan = Counter((p.get("ket_luan") or "").strip().lower() for p in da_doc)
    ngoai_danh_sach = [p["ca"] for p in phieu if (p.get("ket_luan") or "").strip() and (p["ket_luan"].strip().lower() not in KET_LUAN_HOP_LE)]
    chua_doc = len(ca) - len(da_doc)
    d = ["CHẾ ĐỘ BÓNG — tổng hợp", "=" * 54]
    d.append(f"Tệp: {len(tep)} (đọc được {sum(1 for t in tep if t.get('doc_duoc'))}, bỏ qua {sum(1 for t in tep if t.get('bo_qua'))})")
    d.append(f"Ca (phát hiện): {len(ca)}")
    for khoa, ten in (("tool", "theo công cụ"), ("muc", "theo mức độ"), ("kind", "theo loại")):
        d.append(f"  {ten}: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(c[khoa] for c in ca).items(), key=lambda x: -x[1])))
    d.append("Bất biến vi phạm: " + (", ".join(f"{k}={v}" for k, v in vi_pham.items()) if vi_pham else "không"))
    d.append(f"Đã có người đọc: {len(da_doc)}/{len(ca)} (chưa đọc {chua_doc})")
    if da_doc:
        d.append("Kết luận: " + ", ".join(f"{k}={ket_luan.get(k, 0)}" for k in KET_LUAN_HOP_LE))
        oan = ket_luan.get("oan", 0)
        d.append(f"Tỉ lệ báo oan trên ca đã đọc: {100 * oan / len(da_doc):.0f}%")
    if ngoai_danh_sach:
        d.append(f"CẢNH BÁO: {len(ngoai_danh_sach)} ca có `ket_luan` ngoài {KET_LUAN_HOP_LE}: không tính là đã đọc")
    thoat = 1 if vi_pham else 0
    if doi_du_nguoi_doc and chua_doc:
        thoat = 1
        d.append(f"CHƯA ĐẠT: còn {chua_doc} ca chưa có kết luận hợp lệ (mọi ca lệch phải có người đọc)")
    d.append("KẾT LUẬN: " + ("CHƯA ĐẠT" if thoat else "đạt các điều kiện đã chọn") + ". Công cụ không biết phát hiện nào đúng nghiệp vụ; cần người đọc phiếu.")
    return "\n".join(d), thoat


def tra_cuu(kn: Any, thu_muc: Path, ca_id: str) -> str:
    """Nội dung của MỘT ca, ra màn hình (không ghi tệp): chạy lại tệp rồi tìm ca có mã băm này."""
    for p in sorted(thu_muc.glob("*.xlsx")):
        loai = loai_cua_tep(p.name)
        if loai is None:
            continue
        du_lieu = p.read_bytes()
        _, kq = kn.goi(loai[0], p.name, du_lieu)
        tep = hashlib.sha256(du_lieu).hexdigest()[:12]
        for i, f in enumerate(_phat_hien_cua(kq)):
            if dong_ca(tep, loai[0], f, i)["ca"] == ca_id:
                return f"Tệp: {p.name}\n" + json.dumps(f, ensure_ascii=False, indent=2)
    return f"Không thấy ca {ca_id} trong {thu_muc}"


# ---------------------------------------------------------------------------
# Dữ liệu hư cấu (không dữ liệu khách)
# ---------------------------------------------------------------------------

_NHOM = ("Dầu động cơ", "Dầu thuỷ lực", "Mỡ bò", "Dầu hộp số", "Nước làm mát", "Dầu phanh", "Dầu cầu", "Dầu máy nén khí")
_QC = ("phuy 200L", "thùng 18L", "can 5L", "xô 15kg", "chai 1L")


def sinh_ton_kho(duong: Path, so_dong: int, rng: random.Random, tien_to: str = "HC", ten_cong_ty: str = "CÔNG TY HƯ CẤU", ten_nhom: Optional[str] = None) -> Path:
    """Một bảng Nhập-Xuất-Tồn hư cấu, bố cục MISA kiểu A, có gieo lỗi tự nhiên: tồn âm, xuất không có nhập, giá trị bằng 0 mà còn số lượng, lệch cân đối."""
    from openpyxl import Workbook

    rows: list[list[Any]] = [[ten_cong_ty], ["MST: 0000000000"], [], ["BẢNG TỔNG HỢP NHẬP - XUẤT - TỒN"], ["Từ ngày 01/01/2026 đến ngày 30/06/2026"], []]
    rows.append(["Tên kho", "Mã hàng", "Tên hàng", "ĐVT", "Đầu kỳ", "", "", "Nhập kho", "", "", "Xuất kho", "", "", "Cuối kỳ", "", ""])
    rows.append(["", "", "", ""] + ["Số lượng", "Giá trị", "Đơn giá BQ"] * 4)
    def dv(q: float, v: float) -> float:
        """Đơn giá BQ = giá trị / số lượng, như bản xuất thật: bộ đọc coi đơn giá lệch khỏi phép chia là dấu hiệu LỆCH CỘT và từ chối cả tệp."""
        return 0.0 if q == 0 else round(v / q, 2)

    for i in range(so_dong):
        gia = rng.choice((85_000, 120_000, 450_000, 1_020_000, 3_350_000, 4_300_000))
        dk, nhap = rng.randint(0, 40), rng.randint(0, 60)
        xuat = min(dk + nhap, rng.randint(0, 80)) if rng.random() > 0.12 else dk + nhap + rng.randint(1, 15)    # 12%: xuất quá số có -> tồn âm
        ck = dk + nhap - xuat
        gv = 0 if rng.random() < 0.06 else gia                                              # 6%: giá trị xuất bằng 0 mà còn số lượng
        lech = rng.randint(1, 9) * gia if (rng.random() < 0.08 and ck != 0) else 0           # 8%: giá trị cuối kỳ lệch cân đối (đơn giá tính lại theo giá trị lệch)
        v_dk, v_nhap, v_xuat, v_ck = dk * gia, nhap * gia, xuat * gv, ck * gia + lech
        ten = f"{ten_nhom or rng.choice(_NHOM)} {tien_to}{i:03d} {rng.choice(_QC)}"
        rows.append([
            "Kho Hư Cấu", f"{tien_to}-{i:03d}", ten, "phuy",
            dk, v_dk, dv(dk, v_dk), nhap, v_nhap, dv(nhap, v_nhap), xuat, v_xuat, dv(xuat, v_xuat), ck, v_ck, dv(ck, v_ck),
        ])
    rows += [[], ["", "", "Tổng cộng"] + [""] * 13]
    wb = Workbook()
    ws = wb.active
    ws.title = "Tong hop NXT"
    for r in rows:
        ws.append(r)
    duong.parent.mkdir(parents=True, exist_ok=True)
    wb.save(duong)
    return duong


def sinh_hu_cau(thu_muc: Path, so_tep: int, so_dong: int = 40, seed: int = 20261122) -> list[Path]:
    rng = random.Random(seed)
    return [sinh_ton_kho(thu_muc / f"ton_kho_hu_cau_{i + 1:02d}.xlsx", so_dong, rng, tien_to=f"K{i + 1:02d}") for i in range(so_tep)]


# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)       # httpx ghi mỗi lời gọi ở mức INFO: ồn, và vô ích với người đọc phiếu
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thu-muc", type=Path, help="thư mục chứa tệp .xlsx cần chạy")
    ap.add_argument("--sinh-hu-cau", type=int, metavar="N", help="sinh N tệp tồn kho hư cấu vào thư mục tạm rồi chạy")
    ap.add_argument("--ra", type=Path, default=Path("ket_qua_bong"), help="thư mục ghi ca.jsonl và phieu_doc.csv")
    ap.add_argument("--url", help="Brain đang chạy; bỏ trống thì chạy trong tiến trình")
    ap.add_argument("--tong-hop", type=Path, metavar="THU_MUC_KET_QUA", help="chỉ in bảng tổng hợp của một lần chạy")
    ap.add_argument("--doi-du-nguoi-doc", action="store_true", help="thoát 1 nếu còn ca chưa có kết luận hợp lệ trong phiếu")
    ap.add_argument("--tra-cuu", metavar="CA_ID", help="in nội dung của một ca (cần --thu-muc), chỉ ra màn hình")
    a = ap.parse_args(argv)

    if a.tong_hop:
        bang, thoat = tong_hop(a.tong_hop, a.doi_du_nguoi_doc)
        print(bang)
        return thoat

    kn = KetNoi(a.url)
    if a.tra_cuu:
        if not a.thu_muc:
            ap.error("--tra-cuu cần --thu-muc")
        print(tra_cuu(kn, a.thu_muc, a.tra_cuu))
        return 0

    tam = None
    thu_muc = a.thu_muc
    if a.sinh_hu_cau:
        tam = tempfile.TemporaryDirectory(prefix="bong_hu_cau_")
        thu_muc = Path(tam.name)
        sinh_hu_cau(thu_muc, a.sinh_hu_cau)
    if not thu_muc:
        ap.error("cần --thu-muc hoặc --sinh-hu-cau")
    try:
        dong = chay_thu_muc(kn, thu_muc)
    finally:
        if tam:
            tam.cleanup()
    ghi_ket_qua(dong, a.ra)
    bang, thoat = tong_hop(a.ra, a.doi_du_nguoi_doc)
    print(bang)
    print(f"\nĐã ghi: {a.ra / 'ca.jsonl'}, {a.ra / 'phieu_doc.csv'} (điền cột nguoi_doc, ket_luan = {'/'.join(KET_LUAN_HOP_LE)}, ghi_chu)")
    return thoat


if __name__ == "__main__":
    sys.exit(main())
