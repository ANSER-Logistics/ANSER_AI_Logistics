"""
offline_training/make_n8n_bo_loc.py — mẫu n8n "bộ lọc nghiệp vụ": IF là một câu hỏi, nhánh "không" để TRỐNG hoặc có bước riêng.

VÌ SAO CÓ FILE NÀY (#91, anser-v4, chủ dự án chốt làm v5 ngày 19/11/2026)
-------------------------------------------------------------------------
anser-v4 hỏng n8n 14/34 và thử lại không cứu được câu nào: 8 trong 12 lỗi còn lại là nhánh "không" của IF nối tới một node
tên `noOp` mà workflow không hề có. DeepSeek làm đúng cả 34, v3 đúng 33, nên đây là thói quen của model, không phải đề hỏng.

Dữ liệu huấn luyện n8n đúng khuôn runtime hiện chỉ có 36 workflow mẫu thật của Body. Đo ngày 19/11: cả 36 node IF của chúng là
MỆNH ĐỀ BẢO VỆ (`Valid?`, `Authorized?` rồi `Trả 400`); 31 trong 36 có cả hai nhánh nối tới một node. Đề đo thì có 23 câu hỏi
IF, phần lớn là BỘ LỌC NGHIỆP VỤ ("Có hàng nào dưới ngưỡng?", rồi dựng cảnh báo, rồi gửi): kế hoạch không có bước nào cho nhánh
"không" vì nhánh đó chỉ là không làm gì. Dữ liệu chưa bao giờ dạy: *kế hoạch im lặng về nhánh không thì để nhánh đó trống*.

KHÔNG làm bằng cách bỏ node lá khỏi workflow mẫu thật (đã thử và bỏ): 14 trong 15 node lá đó là `Respond 400`, tức phản hồi khi xác
thực hoặc kiểm tra đầu vào thất bại. Dạy model bỏ nó là dạy một workflow webhook không trả lời khi bị từ chối.

HAI HỌ, CÓ CHỦ ĐÍCH ĐỐI LẬP
---------------------------
  - nhánh "không" TRỐNG (70%): kế hoạch là chuỗi tuyến tính, IF là câu hỏi, không có bước nào cho nhánh không.
  - nhánh "không" CÓ BƯỚC (30%): kế hoạch có thêm một bước nói thẳng kết quả "không" ("Báo không có chuyến nào trễ"); bước đó
    phải được nối vào output 1. Nếu chỉ có họ thứ nhất, model học "IF thì không bao giờ nối nhánh không", cũng sai.

KHÔNG TRÙNG BỘ ĐO. Mọi bước của mẫu sinh ra khác mọi bước của `make_n8n_eval.DE_BAI` (so khớp bỏ dấu, không phân biệt hoa thường);
vi phạm là AssertionError, không phải cảnh báo. Mẫu hoàn toàn hư cấu; tham số lấy từ chính ví dụ trong catalog nên mẫu luôn qua
`validate_workflow`.

CHẠY (không cần GPU, không cần API):  python offline_training/make_n8n_pairs.py --bo-loc 90
"""

from __future__ import annotations

import copy
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.dgen_common import strip_diacritics  # noqa: E402

# (cụm lịch, cron)
LICH = [
    ("Mỗi 6 tiếng", "0 */6 * * *"), ("Mỗi chiều 18h", "0 18 * * *"), ("Mỗi thứ Sáu 17h", "0 17 * * 5"),
    ("Mỗi sáng 6h30", "30 6 * * *"), ("Mỗi tháng ngày 5", "0 8 5 * *"), ("Mỗi thứ Tư 9h", "0 9 * * 3"),
    ("Mỗi 12 tiếng", "0 */12 * * *"), ("Mỗi cuối tuần", "0 8 * * 6"),
]

# Mỗi đối tượng: cách lấy, câu hỏi IF, cách dựng, và bước "không có gì" cho họ có-bước.
DOI_TUONG: list[dict[str, Any]] = [
    {"lay": "Đọc danh sách chuyến xe đang chạy", "sql": "SELECT trip_id, delay_minutes FROM trips WHERE status = 'running'",
     "sheet": None, "hoi": "Có chuyến nào trễ giờ?", "field": "late_count", "dung": "Soạn danh sách chuyến trễ",
     "khong": "Báo không có chuyến nào trễ"},
    {"lay": "Đọc đơn đặt hàng chờ duyệt", "sql": "SELECT order_id, waiting_days FROM orders WHERE status = 'pending'",
     "sheet": None, "hoi": "Có đơn nào chờ quá 2 ngày?", "field": "stale_orders", "dung": "Soạn nhắc duyệt đơn",
     "khong": "Báo không còn đơn tồn"},
    {"lay": "Đọc hạn đăng kiểm của đội xe", "sql": None, "sheet": "VehicleInspection",
     "hoi": "Có xe nào sắp hết hạn đăng kiểm?", "field": "expiring", "dung": "Soạn danh sách xe cần đăng kiểm",
     "khong": "Báo đội xe còn hạn"},
    {"lay": "Đọc hợp đồng với nhà xe", "sql": None, "sheet": "CarrierContracts",
     "hoi": "Có hợp đồng nào sắp hết hạn?", "field": "contracts_ending", "dung": "Soạn nhắc gia hạn hợp đồng",
     "khong": "Báo hợp đồng còn hiệu lực"},
    {"lay": "Đọc phiếu chi trong ngày", "sql": "SELECT voucher_id, has_attachment FROM vouchers WHERE created_at >= CURRENT_DATE",
     "sheet": None, "hoi": "Có phiếu chi nào thiếu chứng từ?", "field": "missing_docs", "dung": "Soạn danh sách phiếu thiếu chứng từ",
     "khong": "Báo phiếu chi đều đủ chứng từ"},
    {"lay": "Đọc hoá đơn nhà xe chưa nhận", "sql": None, "sheet": "CarrierInvoices",
     "hoi": "Có nhà xe nào chưa gửi hoá đơn?", "field": "missing_invoices", "dung": "Soạn nhắc nhà xe gửi hoá đơn",
     "khong": "Báo đã nhận đủ hoá đơn"},
    {"lay": "Đọc doanh thu bán dầu trong ngày", "sql": "SELECT SUM(amount) AS revenue FROM sales_invoices WHERE issued_at >= CURRENT_DATE",
     "sheet": None, "hoi": "Doanh thu thấp hơn mức hôm qua?", "field": "revenue_drop", "dung": "Soạn cảnh báo doanh thu giảm",
     "khong": "Báo doanh thu bình thường"},
    {"lay": "Đọc tài xế chưa nộp giấy tờ", "sql": None, "sheet": "DriverPapers",
     "hoi": "Có tài xế nào thiếu giấy tờ?", "field": "missing_papers", "dung": "Soạn danh sách tài xế thiếu giấy tờ",
     "khong": "Báo giấy tờ tài xế đã đủ"},
    {"lay": "Đọc lượng dầu nhớt xuất theo kho", "sql": "SELECT warehouse, SUM(quantity) AS out_qty FROM stock_moves GROUP BY warehouse",
     "sheet": None, "hoi": "Có kho nào xuất vượt kế hoạch?", "field": "over_plan", "dung": "Soạn báo cáo kho xuất vượt",
     "khong": "Báo các kho trong kế hoạch"},
    {"lay": "Đọc khách có phiếu thu chưa khớp", "sql": None, "sheet": "UnmatchedReceipts",
     "hoi": "Có phiếu thu nào chưa khớp khách?", "field": "unmatched", "dung": "Soạn danh sách phiếu thu chưa khớp",
     "khong": "Báo mọi phiếu thu đã khớp"},
]

# (tên bước, loại: discord | email). Khác hẳn "Gửi Discord", "Gửi email ..." của bộ đo.
KENH = [("Báo lên kênh Discord điều hành", "discord"), ("Đẩy cảnh báo sang Discord kế toán", "discord"),
        ("Chuyển thư cho trưởng bộ phận", "email"), ("Nhắn qua email điều phối", "email")]


# Số lần ghép liền nhau ra bản đã có thì coi như hết tổ hợp (không phải đoán trước số tổ hợp).
HET_CACH_GHEP = 2_000


def _chuan(s: str) -> str:
    return " ".join(strip_diacritics(s).lower().split())


def buoc_cua_bo_do() -> set[str]:
    """Mọi bước của bộ đo n8n, đã chuẩn hoá — mẫu sinh ra không được dùng lại bất kỳ bước nào."""
    from offline_training.make_n8n_eval import DE_BAI
    return {_chuan(b) for _, _, bs in DE_BAI for b in bs}


def _node(cat: dict, loai: str, ten: str, x: int, y: int, **tham_so) -> dict[str, Any]:
    meta = cat[f"n8n-nodes-base.{loai}"]
    p = copy.deepcopy(meta.get("example", {}))
    p.update(tham_so)
    return {"name": ten, "type": f"n8n-nodes-base.{loai}", "typeVersion": meta["typeVersion"],
            "position": [x, y], "parameters": p}


def _lien_ket(tu: str, den: list[str]) -> dict:
    return {"main": [[{"node": d, "type": "main", "index": 0} for d in den]]}


def dung_mau(cat: dict, rng: random.Random, co_buoc_khong: bool) -> dict[str, Any]:
    """Một cặp `{task, plan, answer}`. `co_buoc_khong`: kế hoạch có bước riêng cho nhánh "không" (họ có-bước)."""
    lich_txt, cron = rng.choice(LICH)
    dt = rng.choice(DOI_TUONG)
    kenh_txt, kenh_loai = rng.choice(KENH)
    ghi_nhat_ky = rng.random() < 0.3

    if dt["sql"] and ("postgres" in {k.split(".")[-1] for k in cat}):
        lay = ("postgres", {"operation": "executeQuery", "query": dt["sql"]})
    else:
        lay = ("googleSheets", {"sheetName": dt["sheet"] or "Sheet1"})
    if rng.random() < 0.5:
        dk = {"conditions": {"boolean": [{"value1": "={{ $json.%s }}" % dt["field"], "value2": True}]}}
    else:
        dk = {"conditions": {"number": [{"value1": "={{ $json.%s }}" % dt["field"], "operation": "larger",
                                         "value2": rng.choice([0, 1, 3, 5])}]}}
    soan = {"assignments": {"assignments": [{"name": "message", "value": "=" + dt["dung"] + " {{ $json.%s }}" % dt["field"],
                                             "type": "string"}]}}

    buoc = [lich_txt, dt["lay"], dt["hoi"], dt["dung"], kenh_txt]
    if ghi_nhat_ky:
        buoc.append("Ghi lại lần đã báo")
    if co_buoc_khong:
        buoc.append(dt["khong"])

    nodes = [
        _node(cat, "scheduleTrigger", lich_txt, 0, 300, rule={"interval": [{"field": "cronExpression", "expression": cron}]}),
        _node(cat, lay[0], dt["lay"], 250, 300, **lay[1]),
        _node(cat, "if", dt["hoi"], 500, 300, **dk),
        _node(cat, "set", dt["dung"], 750, 300, **soan),
        _node(cat, "httpRequest" if kenh_loai == "discord" else "emailSend", kenh_txt, 1000, 300),
    ]
    con = {
        lich_txt: _lien_ket(lich_txt, [dt["lay"]]),
        dt["lay"]: _lien_ket(dt["lay"], [dt["hoi"]]),
        dt["hoi"]: {"main": [[{"node": dt["dung"], "type": "main", "index": 0}], []]},   # nhánh "không" TRỐNG
        dt["dung"]: _lien_ket(dt["dung"], [kenh_txt]),
    }
    if ghi_nhat_ky:
        nodes.append(_node(cat, "googleSheets", "Ghi lại lần đã báo", 1250, 300, sheetName="NotificationLog"))
        con[kenh_txt] = _lien_ket(kenh_txt, ["Ghi lại lần đã báo"])
    if co_buoc_khong:
        nodes.append(_node(cat, "httpRequest" if kenh_loai == "discord" else "emailSend", dt["khong"], 750, 500))
        con[dt["hoi"]]["main"][1] = [{"node": dt["khong"], "type": "main", "index": 0}]

    ten = f"{dt['hoi'].rstrip('?')} ({lich_txt.lower()})"
    answer = {"action": "create_workflow", "name": ten, "payload": {"nodes": nodes, "connections": con}}
    task = f'Dựng workflow n8n "{ten}" gồm các bước: {", ".join(buoc)}.'
    plan = "[PLAN]\n" + "\n".join(f"{i}. {b}" for i, b in enumerate(buoc, 1))
    return {"task": task, "plan": plan, "answer": answer, "buoc": buoc, "co_buoc_khong": co_buoc_khong}


def sinh(cat: dict, n: int, seed: int = 20261119, ty_le_co_buoc: float = 0.3) -> list[dict[str, Any]]:
    """`n` mẫu khác nhau (theo kế hoạch), không dùng bước nào của bộ đo. Hết cách ghép khác nhau thì dừng sớm, không lặp."""
    rng = random.Random(seed)
    cam = buoc_cua_bo_do()
    ra: list[dict[str, Any]] = []
    da_thay: set[str] = set()
    trung_lien_tiep = 0
    while len(ra) < n and trung_lien_tiep < HET_CACH_GHEP:
        m = dung_mau(cat, rng, co_buoc_khong=rng.random() < ty_le_co_buoc)
        trung = [b for b in m["buoc"] if _chuan(b) in cam]
        assert not trung, f"mẫu sinh ra dùng lại bước của bộ đo: {trung}"
        if m["plan"] in da_thay:
            trung_lien_tiep += 1          # ghép ra bản đã có: lặp liền nhau đủ lâu nghĩa là hết tổ hợp khác nhau
            continue
        trung_lien_tiep = 0
        da_thay.add(m["plan"])
        m["_id"] = f"n8n_bo_loc_{len(ra):03d}"
        m["_source"] = "n8n_bo_loc"
        ra.append(m)
    return ra
