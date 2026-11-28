"""
Kiểm cả chuỗi QUA CHÍNH API CỦA BODY, đúng những gì màn hình sẽ gọi trong buổi demo: đăng nhập, trạng thái AI, nạp bảng N-X-T, so hai bản xuất, soi công nợ (màn Dòng tiền), báo cáo lãi lỗ,
khách hàng, các trang dashboard, khung chat; với `--thu-tai-lieu`: nạp một tài liệu phải bị từ chối mà Brain vẫn sống.
Mọi đáp án tính trước từ dữ liệu hư cấu (bộ sinh mẫu của Brain và `demo_ky_vong.json` của `gieo_du_lieu_demo.py`). Mã thoát 0 khi mọi bước bắt buộc đạt.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from offline_training.demo_colab import cham_doc_hoa_don  # noqa: E402
from offline_training.demo_mot_may.body_api import Body, thu_muc_demo  # noqa: E402
from offline_training.kiem_tich_hop_body import DAT  # noqa: E402
from sample_data.make_sample_data import (  # noqa: E402
    CAU_HOI_QUY_CHE,
    DANH_MUC,
    DAP_AN_QUY_CHE,
    DOI_TAC,
    DONG,
    DONG_BAN_SAU,
    HOA_DON_CUOC,
    KY_DEN_SAU,
    LECH_HOA_DON,
    LOI_DOI_TAC,
    LOI_GIEO,
    LOI_HOI_TO,
    QUY_CHE,
    TEN_QUY_CHE,
    ghi_anh_hoa_don,
    ghi_danh_muc,
    ghi_doi_tac,
    ghi_xlsx,
)

GOC = thu_muc_demo()

KET: list[tuple[str, str, str]] = []


def ghi(ten: str, dat: bool | str, chi_tiet: str) -> None:
    tt = dat if isinstance(dat, str) else ("ĐẠT" if dat else "TRƯỢT")
    KET.append((tt, ten, chi_tiet))


def kiem_phan_can_model(b: Body) -> None:
    """Những thứ chỉ chạy khi Brain có model thật (offline_training/demo_colab.py): đọc ảnh hoá đơn cước, nạp tài liệu, hỏi chat về tài liệu đó, rồi xoá để nạp trực tiếp khi demo."""
    tong = int(HOA_DON_CUOC["total"])
    with tempfile.TemporaryDirectory() as tam:
        for ten, lech, duyet in (("doc_hoa_don_dung", 0, False), ("doc_hoa_don_sai_tong", LECH_HOA_DON, True)):
            f = ghi_anh_hoa_don(Path(tam) / f"{ten}.png", lech)
            t0 = time.perf_counter()
            ma, r = b.goi("POST", "/api/ai/freight-invoice", files={"file": (f.name, f.read_bytes())}, han=300)
            tt, ct = cham_doc_hoa_don(ma, r, tong + lech, duyet)
            ghi(ten, tt == DAT, f"{ct} sau {time.perf_counter() - t0:.1f}s")
    ma, r = b.goi("POST", "/api/ai/documents", files={"file": (TEN_QUY_CHE, QUY_CHE.encode("utf-8"))}, han=600)
    ghi("nap_tai_lieu", ma == 200 and isinstance(r, dict) and bool(r.get("chunks")), f"http={ma} {str(r)[:150]}")
    ma, r = b.goi("GET", "/api/ai/documents", han=60)
    co = ma == 200 and any(d.get("source") == TEN_QUY_CHE for d in (r.get("documents") or []))
    ghi("liet_ke_tai_lieu", co, f"http={ma}, thấy {TEN_QUY_CHE}: {co}")
    t0 = time.perf_counter()
    ma, r = b.goi("POST", "/api/ai/chat", {"message": CAU_HOI_QUY_CHE}, han=300)
    tra_loi = r.get("reply", "") if isinstance(r, dict) else str(r)
    ghi("chat_hoi_tai_lieu", ma == 200 and DAP_AN_QUY_CHE in tra_loi and "mock_response" not in tra_loi,
        f"http={ma} {tra_loi[:160]!r} sau {time.perf_counter() - t0:.1f}s")
    ma, r = b.goi("DELETE", "/api/ai/documents?" + urllib.parse.urlencode({"source": TEN_QUY_CHE}), han=60)
    ghi("xoa_tai_lieu", ma == 200, f"http={ma} (kho trống lại để nạp trực tiếp khi demo)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3100")
    che_do = ap.add_mutually_exclusive_group()
    che_do.add_argument("--thu-tai-lieu", action="store_true",
                        help="gửi một tài liệu hư cấu vào kho tri thức: phải bị từ chối và Brain vẫn sống. CHỈ dùng khi kho tri thức đã tắt (bat_demo.ps1 tắt); bật kho thì lệnh này nạp tài liệu thật.")
    che_do.add_argument("--co-model", action="store_true",
                        help="Brain có model thật (Colab): chat không được là mock; đọc ảnh hoá đơn, nạp rồi hỏi tài liệu phải đạt")
    a = ap.parse_args(argv)
    b = Body(a.url)

    ma, _ = b.goi("GET", "/api/ai/health")
    ghi("chua_dang_nhap_bi_chan", ma == 401, f"/api/ai/health khi chưa đăng nhập → {ma}")
    b.dang_nhap()
    ghi("dang_nhap_demo", True, "tài khoản demo vào được")

    ma, h = b.goi("GET", "/api/ai/health")
    ok = ma == 200 and h.get("configured") and h.get("ok") and h.get("auth_enabled") is True and not h.get("canh_bao") and not h.get("degraded")
    ghi("trang_thai_ai", ok, f"configured={h.get('configured')} ok={h.get('ok')} auth_enabled={h.get('auth_enabled')} degraded={h.get('degraded')} canh_bao={h.get('canh_bao')!r}")

    with tempfile.TemporaryDirectory() as tam:
        truoc = ghi_xlsx(Path(tam) / "ton_kho_mau.xlsx")
        sau = ghi_xlsx(Path(tam) / "ton_kho_mau_ban_sau.xlsx", KY_DEN_SAU, DONG_BAN_SAU)
        t0 = time.perf_counter()
        ma, r = b.goi("POST", "/api/ai/inventory-audit", files={"file": (truoc.name, truoc.read_bytes())})
        audit = r.get("audit") if isinstance(r, dict) else None
        ma_loi = {f["code"] for f in (audit or {}).get("findings", [])}
        ghi("nap_ton_kho", ma == 200 and r["import"]["rows_parsed"] == len(DONG) and ma_loi == set(LOI_GIEO),
            f"{r['import']['rows_parsed'] if ma == 200 else r} dòng, {len((audit or {}).get('findings', []))} phát hiện trên {len(ma_loi)} mã, {time.perf_counter() - t0:.1f}s")
        t0 = time.perf_counter()
        ma, r = b.goi("POST", "/api/ai/period-diff", files={"truoc": (truoc.name, truoc.read_bytes()), "sau": (sau.name, sau.read_bytes())})
        hien = {f["code"]: f["kind"] for f in r.get("findings", [])} if isinstance(r, dict) else {}
        tong = r.get("summary", {}).get("tổng_tiền_ảnh_hưởng") if isinstance(r, dict) else None
        ghi("so_hai_ban", ma == 200 and hien == LOI_HOI_TO and not r.get("warnings"), f"{len(hien)} chỗ sửa hồi tố, tổng ảnh hưởng {tong}, {time.perf_counter() - t0:.1f}s")

    with tempfile.TemporaryDirectory() as tam:
        for vai_tro, ten_tep in (("khách hàng", "khach_hang_mau.xlsx"), ("nhà cung cấp", "nha_cung_cap_mau.xlsx")):
            f = ghi_doi_tac(Path(tam) / ten_tep, vai_tro)
            ma, r = b.goi("POST", "/api/ai/partner-audit", files={"file": (f.name, f.read_bytes())})
            im = r.get("import", {}) if isinstance(r, dict) else {}
            thuc_te = sorted((x["kind"], x.get("code") or "") for x in ((r.get("audit") or {}).get("findings", []) if isinstance(r, dict) else []))
            ghi(f"cong_no_{'khach' if vai_tro == 'khách hàng' else 'ncc'}",
                ma == 200 and im.get("role") == vai_tro and im.get("rows_parsed") == len(DOI_TAC[vai_tro]) and thuc_te == sorted(LOI_DOI_TAC[vai_tro]),
                f"http={ma} {im.get('rows_parsed')} dòng, vai trò {im.get('role')!r}, {len(thuc_te)} điểm cần xem (đáp án {len(LOI_DOI_TAC[vai_tro])})")

    with tempfile.TemporaryDirectory() as tam:
        f = ghi_danh_muc(Path(tam) / "danh_muc_hang_hoa_mau.xlsx")
        ma, r = b.goi("POST", "/api/ai/vat-catalog", files={"file": (f.name, f.read_bytes())})
        s = ((r.get("audit") or {}).get("summary") or {}) if isinstance(r, dict) else {}
        thuc = (s.get("số_mã"), s.get("tra_ra_8%"), s.get("tra_ra_10%"), s.get("không_tra_được"))
        mong = (len(DANH_MUC), *(sum(1 for _, _, kl in DANH_MUC if kl == k) for k in ("8%", "10%", "?")))
        ghi("soat_thue_suat", ma == 200 and thuc == mong, f"http={ma} (mã, 8%, 10%, cần kế toán) = {thuc}, đáp án {mong}")

    ma, r = b.goi("GET", "/api/customers")
    so_khach = len(r.get("customers", [])) if isinstance(r, dict) else 0
    ghi("khach_hang", ma == 200 and so_khach >= 4, f"trang Khách hàng có {so_khach} khách")

    kv_tep = GOC / "log" / "demo_ky_vong.json"
    ma, r = b.goi("GET", "/api/ai/report?granularity=month")
    if not kv_tep.exists():
        ghi("bao_cao", "TRƯỢT", "chưa gieo dữ liệu demo (không có demo_ky_vong.json)")
    elif ma != 200:
        ghi("bao_cao", False, f"http={ma} {r}")
    else:
        kv = json.loads(kv_tep.read_text(encoding="utf-8"))
        sai = []
        for p in r["report"]["periods"]:
            k = kv.get(p["period"])
            if k is None:
                sai.append(f"{p['period']}: không có trong đáp án")
                continue
            lai = k["revenue_with_cogs"] - k["cogs"]
            if p["revenue"] != round(k["revenue"]) or p["gross_profit"] != round(lai):
                sai.append(f"{p['period']}: doanh thu {p['revenue']} (phải {k['revenue']}), lãi gộp {p['gross_profit']} (phải {lai})")
        cov = r["report"]["explain"]["cogs_coverage_pct"]
        ky = [p["period"] for p in r["report"]["periods"]]
        ghi("bao_cao", not sai and len(ky) >= 3, "; ".join(sai) if sai else f"{len(ky)} kỳ ({ky[0]}..{ky[-1]}) khớp đáp án; phủ giá vốn {cov}%, tin cậy '{r['report']['explain']['confidence']}', {len(r['report']['warnings'])} cảnh báo")

    for trang in ("/dashboard", "/dashboard/inventory", "/dashboard/reports", "/dashboard/audit"):
        ma, _ = b.goi("GET", trang)
        ghi(f"trang{trang.replace('/', '_')}", ma == 200, f"{trang} → {ma}")

    t0 = time.perf_counter()
    ma, r = b.goi("POST", "/api/ai/chat", {"message": "Xin chào, bạn giúp được gì cho kho của tôi?"}, han=300)
    tra_loi = r.get("reply", "") if isinstance(r, dict) else str(r)
    if ma == 200 and "mock_response" in tra_loi:
        ghi("khung_chat", "TRƯỢT" if a.co_model else "MOCK", f"khách sẽ thấy nguyên văn: {tra_loi[:70]} (đừng mở khung chat; Body#41)")
    else:
        ghi("khung_chat", ma == 200 and bool(tra_loi), f"http={ma} {tra_loi[:100]!r} sau {time.perf_counter() - t0:.1f}s")

    if a.thu_tai_lieu:
        ma, r = b.goi("POST", "/api/ai/documents", files={"file": ("tai_lieu_mau.txt", "Tài liệu hư cấu để kiểm.".encode())}, han=90)
        _, h = b.goi("GET", "/api/ai/health", han=30)
        song = isinstance(h, dict) and h.get("ok") is True
        ghi("nap_tai_lieu", ma >= 400 and song, f"nạp tài liệu → http={ma} (phải bị từ chối: kho tri thức tắt có chủ ý), Brain còn sống: {song}")

    if a.co_model:
        kiem_phan_can_model(b)

    for tt, ten, ct in KET:
        print(f"  {tt:6} {ten:24} {ct}")
    hong = [t for t, _, _ in KET if t == "TRƯỢT"]
    print("KHÔNG ĐẠT" if hong else "ĐẠT (qua chính API của Body)")
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
