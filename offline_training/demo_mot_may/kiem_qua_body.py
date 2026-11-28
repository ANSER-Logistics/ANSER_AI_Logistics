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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from offline_training.demo_mot_may.body_api import Body, thu_muc_demo  # noqa: E402
from sample_data.make_sample_data import (  # noqa: E402
    DOI_TAC,
    DONG,
    DONG_BAN_SAU,
    KY_DEN_SAU,
    LOI_DOI_TAC,
    LOI_GIEO,
    LOI_HOI_TO,
    ghi_doi_tac,
    ghi_xlsx,
)

GOC = thu_muc_demo()

KET: list[tuple[str, str, str]] = []


def ghi(ten: str, dat: bool | str, chi_tiet: str) -> None:
    tt = dat if isinstance(dat, str) else ("ĐẠT" if dat else "TRƯỢT")
    KET.append((tt, ten, chi_tiet))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3100")
    ap.add_argument("--thu-tai-lieu", action="store_true",
                    help="gửi một tài liệu hư cấu vào kho tri thức: phải bị từ chối và Brain vẫn sống. CHỈ dùng khi kho tri thức đã tắt (bat_demo.ps1 tắt); bật kho thì lệnh này nạp tài liệu thật.")
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
    ma, r = b.goi("POST", "/api/ai/chat", {"message": "Xin chào, bạn giúp được gì cho kho của tôi?"}, han=120)
    tra_loi = r.get("reply", "") if isinstance(r, dict) else str(r)
    if ma == 200 and "mock_response" in tra_loi:
        ghi("khung_chat", "MOCK", f"khách sẽ thấy nguyên văn: {tra_loi[:70]} (đừng mở khung chat; Body#41)")
    else:
        ghi("khung_chat", ma == 200 and bool(tra_loi), f"http={ma} {tra_loi[:100]!r} sau {time.perf_counter() - t0:.1f}s")

    if a.thu_tai_lieu:
        ma, r = b.goi("POST", "/api/ai/documents", files={"file": ("tai_lieu_mau.txt", "Tài liệu hư cấu để kiểm.".encode())}, han=90)
        _, h = b.goi("GET", "/api/ai/health", han=30)
        song = isinstance(h, dict) and h.get("ok") is True
        ghi("nap_tai_lieu", ma >= 400 and song, f"nạp tài liệu → http={ma} (phải bị từ chối: kho tri thức tắt có chủ ý), Brain còn sống: {song}")

    for tt, ten, ct in KET:
        print(f"  {tt:6} {ten:24} {ct}")
    hong = [t for t, _, _ in KET if t == "TRƯỢT"]
    print("KHÔNG ĐẠT" if hong else "ĐẠT (qua chính API của Body)")
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
