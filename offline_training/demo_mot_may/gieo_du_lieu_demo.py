"""
Gieo dữ liệu bán hàng HƯ CẤU (ngành dầu nhớt) cho buổi demo, qua chính API của Body, rồi lùi ngày hoá đơn về các tháng trước để báo cáo có nhiều kỳ.

Body không seed hoá đơn bán nào, nên trang Báo cáo sẽ chỉ hiện "Chưa có dòng bán nào" nếu không gieo. Một mặt hàng CỐ Ý không có giá vốn: báo cáo phải nói
"chưa đủ giá vốn" thay vì tính lãi như thể đủ. Đáp án (doanh thu, lãi gộp, phủ giá vốn theo tháng) tính ĐỘC LẬP ở đây từ chính dữ liệu đã gieo và ghi ra log\\demo_ky_vong.json
để `kiem_qua_body.py` đối chiếu. Chạy lại không nhân đôi (nhận ra hoá đơn có ghi chú DỮ LIỆU DEMO).

    python offline_training/demo_mot_may/gieo_du_lieu_demo.py --url http://127.0.0.1:3100   # cần DATABASE_URL (để lùi ngày); bat_demo.ps1 đặt sẵn
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from offline_training.demo_mot_may.body_api import Body, thu_muc_demo  # noqa: E402

GOC = thu_muc_demo()
GHI_CHU = "DỮ LIỆU DEMO"
# (tên, danh mục, đơn vị, tồn ban đầu, giá bán, giá vốn | None = CHƯA BIẾT)
HANG = [
    ("Dầu thuỷ lực AW46 can 18L", "Dầu thuỷ lực", "Can", 600, 420_000, 330_000),
    ("Dầu động cơ diesel CF-4 15W40 phuy 200L", "Dầu động cơ", "Phuy", 150, 5_200_000, 4_300_000),
    ("Dầu hộp số GL-5 90 can 18L", "Dầu bánh răng", "Can", 200, 1_150_000, 940_000),
    ("Mỡ bò chịu nhiệt EP2 xô 15kg", "Mỡ bôi trơn", "Xô", 200, 1_250_000, 980_000),
    ("Nhớt xe máy 4T 0.8L", "Dầu động cơ", "Chai", 3000, 85_000, 62_000),
    ("Dung dịch làm mát phuy 200L", "Dung dịch làm mát", "Phuy", 22, 2_600_000, None),     # còn 17 sau bán: hiện cảnh báo sắp hết
]
# Hàng mẫu mặc định của Body (trục cán, vòng bi, tấm nhôm...) lạc ngành với khách dầu nhớt: gỡ khỏi database DEMO (dòng sổ kho của chúng bị xoá theo).
HANG_MAU_BODY = ["Trục cán inox 304", "Vòng bi công nghiệp", "Tấm nhôm 5mm", "Bulong M10 (hộp 100)", "Motor giảm tốc 1HP"]
# Phiếu nhập gần đây (chỉ số hàng, số lượng, nhà cung cấp, cách hôm nay mấy ngày), đơn giá = giá vốn đã biết.
NHAP = [(0, 60, "Nhà cung cấp Dầu Mẫu Phương Nam", 6), (4, 400, "Nhà cung cấp Dầu Mẫu Phương Nam", 5), (2, 20, "Tổng kho Mẫu Miền Bắc", 2)]
KHACH = ["Cty TNHH Cơ khí Mẫu An", "Garage Mẫu Bình", "Cty Vận tải Mẫu Cường", "Đại lý Mẫu Dũng"]
# Mỗi tháng (0 = tháng này, 1 = tháng trước, ...): các hoá đơn [(khách, [(chỉ số hàng, số lượng)])]. Doanh thu tăng dần để biểu đồ có xu hướng.
LICH = {
    5: [(0, [(0, 20), (4, 120)]), (1, [(2, 4)])],
    4: [(2, [(1, 5), (0, 15)]), (3, [(4, 150), (3, 6)])],
    3: [(0, [(0, 30), (2, 6)]), (1, [(4, 180)]), (2, [(5, 2)])],
    2: [(3, [(1, 8), (4, 200)]), (0, [(0, 35), (3, 10)])],
    1: [(2, [(1, 9), (2, 10)]), (1, [(0, 40), (4, 220)]), (3, [(5, 3)])],
}
# Bán gần đây (cách hôm nay mấy ngày, khách, dòng) để các ô và biểu đồ "7 ngày qua" của Body có số.
GAN_DAY = [(6, 0, [(0, 12), (3, 4)]), (4, 2, [(1, 3), (4, 60)]), (3, 1, [(2, 6)]), (1, 3, [(0, 15), (4, 90)]), (0, 0, [(3, 5), (1, 2)])]


def ngay_cua(lui: int, thu_tu: int, hom_nay: dt.date) -> dt.date:
    """Ngày trong tháng lùi `lui` tháng (lui >= 1)."""
    y, m = hom_nay.year, hom_nay.month - lui
    while m <= 0:
        y, m = y - 1, m + 12
    return dt.date(y, m, min(6 + 7 * thu_tu, 27))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3100")
    a = ap.parse_args(argv)
    b = Body(a.url)
    b.dang_nhap()
    ma, r = b.goi("GET", "/api/sales/invoices?limit=500")
    if ma != 200:
        raise SystemExit(f"không đọc được hoá đơn: http={ma} {r}")
    if any((hd.get("note") or "") == GHI_CHU for hd in r["invoices"]):
        print("Dữ liệu demo đã có, không gieo lại.")
        return 0
    ma, r = b.goi("GET", "/api/warehouses")
    kho = r["warehouses"][0]["id"]
    ma, r = b.goi("GET", "/api/products")
    san_co = {p["name"]: p["id"] for p in r["products"]}
    ids = []
    for ten, dm, dv, ton, gia, von in HANG:
        if ten in san_co:
            ids.append(san_co[ten])
            continue
        ma, r = b.goi("POST", "/api/products", {"name": ten, "category": dm, "unit": dv, "stock": ton, "price": gia, "cost": von, "warehouseId": kho})
        if ma != 201:
            raise SystemExit(f"tạo hàng {ten!r} hỏng: http={ma} {r}")
        ids.append(r["product"]["id"])
    for ten in HANG_MAU_BODY:
        if ten in san_co:
            ma, r = b.goi("DELETE", f"/api/products/{san_co[ten]}")
            if ma not in (200, 204):
                raise SystemExit(f"gỡ hàng mẫu {ten!r} hỏng: http={ma} {r}")

    ma, r = b.goi("GET", "/api/customers")
    if ma != 200:
        raise SystemExit(f"không đọc được khách hàng: http={ma} {r}")
    da_co = {k["name"]: k["id"] for k in r["customers"]}
    khach_ids = []
    for ten in KHACH:
        if ten not in da_co:
            ma, r = b.goi("POST", "/api/customers", {"name": ten, "address": "Hà Nội (hư cấu)", "note": GHI_CHU})
            if ma != 201:
                raise SystemExit(f"tạo khách {ten!r} hỏng: http={ma} {r}")
            da_co[ten] = r["customer"]["id"]
        khach_ids.append(da_co[ten])

    hom_nay = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=7)).date()
    lui_ngay: list[tuple[str, dt.date]] = []
    nhap_ngay: list[tuple[str, dt.date]] = []
    ky_vong: dict[str, dict[str, float]] = defaultdict(lambda: {"revenue": 0, "revenue_with_cogs": 0, "cogs": 0})
    for i, q, ncc, cach in NHAP:
        ma, r = b.goi("POST", "/api/inventory/transactions", {"productId": ids[i], "type": "import", "quantity": q, "unitCost": HANG[i][5], "counterparty": ncc, "note": GHI_CHU})
        if ma != 201:
            raise SystemExit(f"tạo phiếu nhập hỏng: http={ma} {r}")
        nhap_ngay.append((r["transaction"]["id"], hom_nay - dt.timedelta(days=cach)))
    cac_hoa_don = [(ngay_cua(lui, thu_tu, hom_nay), khach, dong) for lui in sorted(LICH, reverse=True) for thu_tu, (khach, dong) in enumerate(LICH[lui])]
    cac_hoa_don += [(hom_nay - dt.timedelta(days=cach), khach, dong) for cach, khach, dong in GAN_DAY]
    for ngay, khach, dong in cac_hoa_don:
        ma, r = b.goi("POST", "/api/sales/invoices", {"customerId": khach_ids[khach], "note": GHI_CHU, "items": [{"productId": ids[i], "quantity": q} for i, q in dong]})
        if ma != 201:
            raise SystemExit(f"tạo hoá đơn hỏng: http={ma} {r}")
        lui_ngay.append((r["invoice"]["id"], ngay))
        ky = ky_vong[f"{ngay:%Y-%m}"]
        for i, q in dong:
            _, _, _, _, gia, von = HANG[i]
            ky["revenue"] += gia * q
            if von is not None:
                ky["revenue_with_cogs"] += gia * q
                ky["cogs"] += von * q

    # Body không cho đặt ngày qua API: lùi `created_at` của hoá đơn và dòng sổ kho tương ứng, 12:00 giờ VN (05:00 UTC, để ngày UTC của Body không lệch).
    import psycopg2

    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        # 05:00 UTC = 12:00 VN; hoá đơn HÔM NAY thì không đặt vào tương lai.
        bay_gio = dt.datetime.now(dt.timezone.utc)
        for gd, ngay in nhap_ngay:
            cur.execute("update inventory_transactions set created_at = %s where id = %s",
                        (min(dt.datetime(ngay.year, ngay.month, ngay.day, 3, 0, tzinfo=dt.timezone.utc), bay_gio), gd))
        for hd, ngay in lui_ngay:
            moc = min(dt.datetime(ngay.year, ngay.month, ngay.day, 5, 0, tzinfo=dt.timezone.utc), bay_gio)
            cur.execute("update sales_invoices set created_at = %s where id = %s", (moc, hd))
            cur.execute("update inventory_transactions set created_at = %s where source_type = 'sale' and source_id = %s", (moc, hd))
    (GOC / "log" / "demo_ky_vong.json").write_text(json.dumps(ky_vong, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã gieo {len(HANG)} mặt hàng, {len(khach_ids)} khách, {len(lui_ngay)} hoá đơn trên {len(ky_vong)} tháng; đáp án ở log\\demo_ky_vong.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
