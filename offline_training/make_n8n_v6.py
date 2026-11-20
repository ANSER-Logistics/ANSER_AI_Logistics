"""
offline_training/make_n8n_v6.py — hai họ mẫu n8n cho anser-v6, rút từ ca hỏng thật của anser-v5 (#91, 20/11/2026).

VÌ SAO CÓ FILE NÀY
------------------
v5 (60 mẫu "bộ lọc nghiệp vụ", `make_n8n_bo_loc.py`) sửa được 8 câu n8n so với v4 nhưng vẫn trượt cổng (29/34, cần 32). Năm câu còn
hỏng sau thử lại, đọc theo hình dạng đề bài (`make_n8n_eval.DE_BAI`):

  1. `gia_canh_bao_bien_mong`, `no_bao_cao_tap_trung`: nhánh "không" của IF nối tới `noOp` không có. Cả hai đề có MỘT BƯỚC TÍNH nằm giữa
     bước lấy dữ liệu và IF ("Tính biên từng mã", "Tính tỷ lệ ba khách lớn nhất"). Họ `bo_loc` luôn là lấy -> IF ngay, nên model chưa từng
     thấy khuôn "lấy -> tính -> IF -> dựng -> gửi". Đó là họ C dưới đây.
  2. `no_doi_chieu_ncc`: trùng tên node "Gửi email từng nhà cung cấp". Bước có chữ "từng" làm model sinh hai node cùng tên (một lần cho
     "từng", một lần cho "gửi"); n8n chạy MỖI node trên từng dòng dữ liệu, nên đúng là MỘT node. Đó là họ B dưới đây.
  3. `hd_luu_tru_hoa_don`: cắt cụt vì model lặp trong một chuỗi tự do của `parameters`. Lỗ hở grammar, KHÔNG sửa bằng dữ liệu: xem #91.
  4. `gia_cap_nhat_bang_gia_khach`: nối tới node `Trả 200` không có. CHƯA có họ cho nó: cần biết n8n làm gì khi nhánh thành công của webhook
     không có node Respond (việc kiểm trên n8n thật, giao Sơn). Dạy một hành vi n8n chưa kiểm là dạy bừa.

KHÔNG TRÙNG BỘ ĐO. Như `make_n8n_bo_loc`: mọi bước khác mọi bước của `make_n8n_eval.DE_BAI` (so khớp bỏ dấu, không phân biệt hoa thường), vi phạm
là AssertionError. Hình dạng thì CÓ cố ý giống đề đo (đó là mục đích: dạy khuôn), nhưng lời lẽ của từng bước thì khác. Mẫu hoàn toàn hư cấu.

CHẠY (không cần GPU, không cần API):  python offline_training/make_n8n_pairs.py --bo-loc 60 --v6 40
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.make_n8n_bo_loc import (  # noqa: E402
    HET_CACH_GHEP,
    KENH,
    LICH,
    _chuan,
    _lien_ket,
    _node,
    buoc_cua_bo_do,
)

# Họ C: lấy -> TÍNH -> IF -> dựng -> gửi. (cách lấy, bước tính, câu hỏi IF, trường, cách dựng, bước "không có gì")
TINH_ROI_LOC: list[dict[str, Any]] = [
    {"lay": "Đọc giá nhập và giá bán dầu nhớt", "sheet": "OilPrices", "tinh": "Tính chênh lệch giá nhập và giá bán", "hoi": "Chênh lệch dưới 5%?",
     "field": "gap_pct", "dung": "Soạn danh sách mã bán lỗ", "khong": "Báo chênh lệch giá ổn"},
    {"lay": "Đọc tồn kho theo mã hàng", "sheet": "StockLevels", "tinh": "Tính số ngày tồn còn lại", "hoi": "Còn dưới 7 ngày?",
     "field": "days_left", "dung": "Soạn đề xuất nhập thêm hàng", "khong": "Báo tồn kho đủ dùng"},
    {"lay": "Đọc công nợ phải thu theo đại lý", "sheet": "DealerDebt", "tinh": "Tính phần trăm nợ của mỗi đại lý", "hoi": "Có đại lý nào quá 30% tổng nợ?",
     "field": "share_pct", "dung": "Soạn cảnh báo nợ tập trung", "khong": "Báo nợ phân bổ đều"},
    {"lay": "Đọc chi phí nhiên liệu theo chuyến", "sheet": "FuelCosts", "tinh": "Tính chi phí nhiên liệu trên mỗi cây số", "hoi": "Vượt định mức?",
     "field": "fuel_per_km", "dung": "Soạn danh sách chuyến tốn nhiên liệu", "khong": "Báo nhiên liệu trong định mức"},
    {"lay": "Đọc doanh thu theo kênh bán", "sheet": "ChannelRevenue", "tinh": "Tính tỷ trọng doanh thu từng kênh", "hoi": "Một kênh chiếm quá 60%?",
     "field": "top_share", "dung": "Soạn cảnh báo phụ thuộc một kênh", "khong": "Báo doanh thu cân bằng giữa các kênh"},
    {"lay": "Đọc đơn hàng đã giao trong tuần", "sheet": "DeliveredOrders", "tinh": "Tính tỷ lệ giao trễ", "hoi": "Tỷ lệ trễ trên 10%?",
     "field": "late_rate", "dung": "Soạn báo cáo giao trễ", "khong": "Báo giao hàng đúng hạn"},
    {"lay": "Đọc hoá đơn mua hàng trong tháng", "sheet": "PurchaseInvoices", "tinh": "Tính tổng tiền theo nhà cung cấp", "hoi": "Có nhà cung cấp nào vượt hạn mức?",
     "field": "over_limit", "dung": "Soạn cảnh báo vượt hạn mức mua", "khong": "Báo mua hàng trong hạn mức"},
    {"lay": "Đọc số vòng quay của từng xe", "sheet": "TruckUtilization", "tinh": "Tính tỷ lệ sử dụng xe", "hoi": "Tỷ lệ sử dụng dưới 50%?",
     "field": "util_rate", "dung": "Soạn danh sách xe chạy ít", "khong": "Báo đội xe được dùng tốt"},
    {"lay": "Đọc số liệu hàng trả lại", "sheet": "ReturnedGoods", "tinh": "Tính tỷ lệ hàng trả lại theo mặt hàng", "hoi": "Có mặt hàng nào trả lại quá 3%?",
     "field": "return_rate", "dung": "Soạn cảnh báo hàng trả lại cao", "khong": "Báo tỷ lệ trả lại bình thường"},
    {"lay": "Đọc giá cước các nhà xe", "sheet": "CarrierRates", "tinh": "Tính mức tăng giá cước so với tháng trước", "hoi": "Có nhà xe nào tăng trên 8%?",
     "field": "rate_rise", "dung": "Soạn cảnh báo cước tăng", "khong": "Báo giá cước ổn định"},
]

# Họ B: bước có chữ "từng" là MỘT node. (cách lấy, cách dựng thư, bước gửi "từng", kênh)
GUI_TUNG: list[dict[str, Any]] = [
    {"lay": "Đọc danh sách đại lý còn nợ", "sheet": "DealersOwing", "dung": "Soạn thư nhắc nợ", "gui": "Gửi thư nhắc từng đại lý", "loai": "emailSend"},
    {"lay": "Đọc lịch giao hàng ngày mai", "sheet": "TomorrowDeliveries", "dung": "Soạn tin báo lịch giao", "gui": "Nhắn Zalo từng tài xế", "loai": "httpRequest"},
    {"lay": "Đọc danh sách xe đến hạn bảo dưỡng", "sheet": "MaintenanceDue", "dung": "Soạn lời nhắc bảo dưỡng", "gui": "Gửi email từng chủ xe", "loai": "emailSend"},
    {"lay": "Đọc đơn hàng đã xuất kho", "sheet": "ShippedOrders", "dung": "Soạn thông báo đã xuất kho", "gui": "Báo qua Zalo từng khách", "loai": "httpRequest"},
    {"lay": "Đọc hợp đồng sắp gia hạn", "sheet": "RenewalContracts", "dung": "Soạn thư đề nghị gia hạn", "gui": "Gửi thư mời từng nhà xe", "loai": "emailSend"},
    {"lay": "Đọc bảng lương tạm tính", "sheet": "DraftPayroll", "dung": "Soạn phiếu lương", "gui": "Gửi phiếu lương từng nhân viên", "loai": "emailSend"},
    {"lay": "Đọc kết quả đối chiếu chuyến", "sheet": "TripReconcile", "dung": "Soạn bảng đối chiếu chuyến", "gui": "Chuyển bảng cho từng điều phối viên", "loai": "emailSend"},
    {"lay": "Đọc danh sách khách mới trong tuần", "sheet": "NewCustomers", "dung": "Soạn lời chào khách mới", "gui": "Gửi lời chào từng khách mới", "loai": "emailSend"},
]


def _lich(rng: random.Random) -> tuple[str, str]:
    return rng.choice(LICH)


def dung_mau_tinh_roi_loc(cat: dict, rng: random.Random, co_buoc_khong: bool) -> dict[str, Any]:
    """Họ C. Kế hoạch: lịch, lấy, TÍNH, IF, dựng, gửi [, bước "không"]. Nhánh "không" trống nếu kế hoạch im lặng, nối bước nếu có."""
    lich_txt, cron = _lich(rng)
    dt = rng.choice(TINH_ROI_LOC)
    kenh_txt, kenh_loai = rng.choice(KENH)
    dk = {"conditions": {"number": [{"value1": "={{ $json.%s }}" % dt["field"], "operation": rng.choice(["larger", "smaller"]),
                                     "value2": rng.choice([3, 5, 7, 10, 30, 50, 60])}]}}
    tinh = {"assignments": {"assignments": [{"name": dt["field"], "value": "={{ $json.value }}", "type": "number"}]}}
    soan = {"assignments": {"assignments": [{"name": "message", "value": "=" + dt["dung"] + " {{ $json.%s }}" % dt["field"],
                                             "type": "string"}]}}
    buoc = [lich_txt, dt["lay"], dt["tinh"], dt["hoi"], dt["dung"], kenh_txt]
    if co_buoc_khong:
        buoc.append(dt["khong"])
    gui = "httpRequest" if kenh_loai == "discord" else "emailSend"
    nodes = [
        _node(cat, "scheduleTrigger", lich_txt, 0, 300, rule={"interval": [{"field": "cronExpression", "expression": cron}]}),
        _node(cat, "googleSheets", dt["lay"], 250, 300, sheetName=dt["sheet"]),
        _node(cat, "set", dt["tinh"], 500, 300, **tinh),
        _node(cat, "if", dt["hoi"], 750, 300, **dk),
        _node(cat, "set", dt["dung"], 1000, 300, **soan),
        _node(cat, gui, kenh_txt, 1250, 300),
    ]
    con = {
        lich_txt: _lien_ket(lich_txt, [dt["lay"]]),
        dt["lay"]: _lien_ket(dt["lay"], [dt["tinh"]]),
        dt["tinh"]: _lien_ket(dt["tinh"], [dt["hoi"]]),
        dt["hoi"]: {"main": [[{"node": dt["dung"], "type": "main", "index": 0}], []]},      # nhánh "không" TRỐNG
        dt["dung"]: _lien_ket(dt["dung"], [kenh_txt]),
    }
    if co_buoc_khong:
        nodes.append(_node(cat, gui, dt["khong"], 1000, 500))
        con[dt["hoi"]]["main"][1] = [{"node": dt["khong"], "type": "main", "index": 0}]
    ten = f"{dt['hoi'].rstrip('?')} ({lich_txt.lower()})"
    return _dong(ten, buoc, nodes, con, "tinh_roi_loc", co_buoc_khong)


def dung_mau_gui_tung(cat: dict, rng: random.Random) -> dict[str, Any]:
    """Họ B. Kế hoạch: lịch, lấy, dựng, GỬI TỪNG [, ghi]. Bước có chữ "từng" là MỘT node, tên không trùng bước nào khác."""
    lich_txt, cron = _lich(rng)
    dt = rng.choice(GUI_TUNG)
    ghi = rng.random() < 0.4
    soan = {"assignments": {"assignments": [{"name": "message", "value": "=" + dt["dung"] + " {{ $json.name }}", "type": "string"}]}}
    buoc = [lich_txt, dt["lay"], dt["dung"], dt["gui"]]
    nodes = [
        _node(cat, "scheduleTrigger", lich_txt, 0, 300, rule={"interval": [{"field": "cronExpression", "expression": cron}]}),
        _node(cat, "googleSheets", dt["lay"], 250, 300, sheetName=dt["sheet"]),
        _node(cat, "set", dt["dung"], 500, 300, **soan),
        _node(cat, dt["loai"], dt["gui"], 750, 300),
    ]
    con = {
        lich_txt: _lien_ket(lich_txt, [dt["lay"]]),
        dt["lay"]: _lien_ket(dt["lay"], [dt["dung"]]),
        dt["dung"]: _lien_ket(dt["dung"], [dt["gui"]]),
    }
    if ghi:
        buoc.append("Ghi lại danh sách đã gửi")
        nodes.append(_node(cat, "googleSheets", "Ghi lại danh sách đã gửi", 1000, 300, sheetName="SentLog"))
        con[dt["gui"]] = _lien_ket(dt["gui"], ["Ghi lại danh sách đã gửi"])
    ten = f"{dt['gui']} ({lich_txt.lower()})"
    return _dong(ten, buoc, nodes, con, "gui_tung", False)


def _dong(ten: str, buoc: list[str], nodes: list, con: dict, ho: str, co_buoc_khong: bool) -> dict[str, Any]:
    answer = {"action": "create_workflow", "name": ten, "payload": {"nodes": nodes, "connections": con}}
    task = f'Dựng workflow n8n "{ten}" gồm các bước: {", ".join(buoc)}.'
    plan = "[PLAN]\n" + "\n".join(f"{i}. {b}" for i, b in enumerate(buoc, 1))
    return {"task": task, "plan": plan, "answer": answer, "buoc": buoc, "co_buoc_khong": co_buoc_khong, "ho": ho}


def sinh(cat: dict, n: int, seed: int = 20261120, ty_le_gui_tung: float = 0.4,
         ty_le_co_buoc: float = 0.3) -> list[dict[str, Any]]:
    """`n` mẫu khác nhau (theo kế hoạch) của hai họ, không dùng bước nào của bộ đo. Hết cách ghép khác nhau thì dừng sớm."""
    rng = random.Random(seed)
    cam = buoc_cua_bo_do()
    ra: list[dict[str, Any]] = []
    da_thay: set[str] = set()
    lap = 0
    while len(ra) < n and lap < HET_CACH_GHEP:
        if rng.random() < ty_le_gui_tung:
            m = dung_mau_gui_tung(cat, rng)
        else:
            m = dung_mau_tinh_roi_loc(cat, rng, co_buoc_khong=rng.random() < ty_le_co_buoc)
        trung = [b for b in m["buoc"] if _chuan(b) in cam]
        assert not trung, f"mẫu sinh ra dùng lại bước của bộ đo: {trung}"
        if m["plan"] in da_thay:
            lap += 1
            continue
        lap = 0
        da_thay.add(m["plan"])
        m["_id"] = f"n8n_v6_{len(ra):03d}"
        m["_source"] = "n8n_v6"
        ra.append(m)
    return ra
