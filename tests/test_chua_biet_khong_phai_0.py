"""
tests/test_chua_biet_khong_phai_0.py — "chưa biết" không được đổi thành 0.

Nguyên tắc của dự án (AGENTS §R1): *thiếu dữ liệu thì nói thiếu, không điền 0*.
Một con số 0 là một PHÉP ĐO ("đã đo, và bằng không"); chưa biết thì chưa đo gì.
Gộp hai thứ đó tạo ra con số trông như kết quả mà không ai kiểm — loại lỗi tệ
nhất vì nó nằm im cho tới lúc quyết toán.

Bộ này khoá bốn chỗ mà đợt soát 12/11/2026 thấy đang làm ngược lại:

  1. `receivables`  — số dư None bị cộng như 0, mẫu số co lại, tỷ lệ tập trung phồng
  2. `reporting`    — kỳ chỉ có chi phí báo "phủ giá vốn 0%" (chưa đo, chứ không phải 0)
  3. `saas_api`     — truy vấn hỏng trả `orders: 0`, model đọc thành "0 đơn"
  4. `chat`        — n8n không trả mã nháp mà vẫn nói "Đã tạo nháp báo giá ?"

Mỗi nhóm có một ca KHÔNG có dữ liệu thiếu để chứng minh sửa không làm nhiễu ca bình thường.
"""

from __future__ import annotations

import json

import pytest

from src.core.partner_import import Partner
from src.core.receivables import audit_partners
from src.core.reporting import ExpenseLine, ReportRequest, SaleLine, build_report

# ---------------------------------------------------------------------------
# 1. Công nợ
# ---------------------------------------------------------------------------


def _khach(*bal):
    return [Partner(code=f"K{i}", name=f"Khách {i}", balance=b) for i, b in enumerate(bal, 1)]


def test_so_du_chua_biet_duoc_dem_chu_khong_bi_im_lang():
    out = audit_partners(_khach(600.0, 400.0, None, None))
    assert out["summary"]["khách_chưa_có_số_dư"] == 2
    assert out["summary"]["nhà_cung_cấp_chưa_có_số_dư"] == 0
    ghi_chu = " ".join(out["summary"]["không_phân_tích_được"])
    assert "CHƯA CÓ số dư" in ghi_chu and "không phải bằng 0" in ghi_chu


def test_ty_le_tap_trung_noi_ro_co_khach_chua_biet_so_du():
    """Khách đầu chiếm 60% — nhưng có 2 khách chưa biết số dư nên 60% chưa phải đủ."""
    out = audit_partners(_khach(600.0, 400.0, None, None))
    tap_trung = [f for f in out["findings"] if f["kind"] == "customer_concentration"]
    assert tap_trung, "ca này phải có phát hiện tập trung"
    assert all(f["evidence"].get("khách_chưa_có_số_dư") == 2 for f in tap_trung)


def test_khong_thieu_so_du_thi_khong_them_nhieu():
    """Ca bình thường: khoá có mặt với giá trị 0, không có ghi chú thêm, bằng chứng không đổi."""
    out = audit_partners(_khach(600.0, 400.0))
    assert out["summary"]["khách_chưa_có_số_dư"] == 0
    assert len(out["summary"]["không_phân_tích_được"]) == 1
    for f in out["findings"]:
        assert "khách_chưa_có_số_dư" not in f["evidence"]


def test_so_du_bang_0_that_khong_bi_coi_la_chua_biet():
    """0 là một phép đo. Chỉ None mới là chưa biết."""
    out = audit_partners(_khach(600.0, 0.0))
    assert out["summary"]["khách_chưa_có_số_dư"] == 0


def test_nha_cung_cap_chua_biet_cung_duoc_dem():
    ncc = [Partner(code="N1", name="NCC 1", balance=None)]
    out = audit_partners(_khach(100.0), ncc)
    assert out["summary"]["nhà_cung_cấp_chưa_có_số_dư"] == 1


# ---------------------------------------------------------------------------
# 2. Báo cáo lãi lỗ
# ---------------------------------------------------------------------------

_CHI_PHI = [ExpenseLine(date="2026-11-03", amount=5_000_000, category="lương")]


def test_chi_co_chi_phi_thi_phu_gia_von_la_chua_biet():
    r = build_report(ReportRequest(sales=[], expenses=_CHI_PHI))
    ex = r["explain"]
    assert ex["cogs_coverage_pct"] is None, "chưa đo, không phải 0%"
    assert ex["confidence"] == "không có dữ liệu"
    assert r["periods"][0]["cogs_coverage_pct"] is None
    assert any("không có doanh thu" in w.lower() for w in r["warnings"])
    # Không được còn câu cảnh báo "Chỉ 0% doanh thu có giá vốn" của nhánh cũ.
    assert not any("Chỉ 0%" in w for w in r["warnings"])


def test_khoa_explain_van_du_de_body_khong_roi_vao_undefined():
    """Hợp đồng với Body: bốn khoá bắt buộc luôn có mặt, kể cả khi giá trị là 'chưa biết'."""
    ex = build_report(ReportRequest(sales=[], expenses=_CHI_PHI))["explain"]
    for k in ("cogs_coverage_pct", "confidence", "formula", "period_count"):
        assert k in ex, f"thiếu khoá {k!r} — Body render sẽ ra undefined"


def test_ky_chi_co_chi_phi_canh_ky_co_doanh_thu():
    """Hai kỳ: một kỳ có bán (đủ giá vốn), một kỳ chỉ có chi phí. Chỉ kỳ thứ hai là None."""
    sales = [SaleLine(date="2026-08-10", revenue=10_000_000, product="A", quantity=1, cogs=6_000_000)]
    chi = [ExpenseLine(date="2026-11-03", amount=1_000_000)]
    r = build_report(ReportRequest(granularity="quarter", sales=sales, expenses=chi, today="2026-11-12"))
    theo_ky = {p["period"]: p for p in r["periods"]}
    co_ban = [p for p in r["periods"] if p["revenue"] > 0]
    chi_phi = [p for p in r["periods"] if p["revenue"] == 0]
    assert len(theo_ky) == 2 and co_ban and chi_phi
    assert co_ban[0]["cogs_coverage_pct"] == 100.0
    assert chi_phi[0]["cogs_coverage_pct"] is None
    # Toàn báo cáo có doanh thu nên vẫn đo được và vẫn "cao"
    assert r["explain"]["cogs_coverage_pct"] == 100.0
    assert r["explain"]["confidence"] == "cao"


def test_co_doanh_thu_nhung_khong_co_gia_von_van_la_0_that():
    """0% ở đây LÀ phép đo (có doanh thu, không dòng nào có giá vốn) — không được đổi thành None."""
    sales = [SaleLine(date="2026-11-03", revenue=10_000_000, product="A", quantity=1, cogs=None)]
    r = build_report(ReportRequest(sales=sales, today="2026-11-12"))
    assert r["explain"]["cogs_coverage_pct"] == 0.0
    assert r["explain"]["confidence"] == "thấp"


# ---------------------------------------------------------------------------
# 3. Báo cáo bán hàng từ DB
# ---------------------------------------------------------------------------


def test_truy_van_hong_thi_so_don_la_chua_biet_khong_phai_0():
    """Kết quả này đi thẳng vào ngữ cảnh model dưới dạng JSON; `orders: 0` thành "0 đơn"."""
    from sqlalchemy import create_engine, text

    from src.core.saas_api import SALES_TABLE, SaasAPI

    api = SaasAPI.__new__(SaasAPI)
    api.engine = create_engine("sqlite://")
    with api.engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {SALES_TABLE} (x INTEGER)"))   # thiếu cột -> truy vấn hỏng
    kq = api.get_sales_report(workspace_id=1, period="today")
    assert kq["revenue"] == "Lỗi"
    assert kq["orders"] is None
    assert "không phải 0" in kq["ghi_chú"]
    # Vẫn là JSON hợp lệ — chat.py json.dumps nó vào prompt.
    assert json.loads(json.dumps(kq, ensure_ascii=False))["orders"] is None


# ---------------------------------------------------------------------------
# 4. Báo giá qua n8n
# ---------------------------------------------------------------------------


def _fake_extract_ok():
    async def fake_extract(msg, history=None):
        return json.dumps({
            "origin": "Hữu Nghị", "destination": "Hải Phòng", "vehicle_type": "5T",
            "cargo_type": "Hàng lạnh", "pickup_date": "2026-07-29",
            "customer_name": "Anh Tuấn", "customer_email": "tuan@minhlong.vn",
        })
    return fake_extract


@pytest.mark.asyncio
@pytest.mark.parametrize("phan_hoi", [{"ok": True}, {"ok": True, "draft_id": ""}, [], None])
async def test_n8n_khong_tra_ma_nhap_thi_khong_tuyen_bo_da_tao(monkeypatch, phan_hoi):
    from src.api import dependencies
    from src.api.routes import chat as chat_mod
    from src.core import utils as utils_mod

    class FakeManager:
        extract_quote_request = staticmethod(_fake_extract_ok())

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return phan_hoi

    class FakeClient:
        async def post(self, url, json=None, timeout=None):
            return FakeResp()

    monkeypatch.setattr(dependencies.runtime, "manager", FakeManager())
    monkeypatch.setenv("N8N_QUOTE_WEBHOOK_URL", "http://n8n.local/webhook/logistics-quote")
    monkeypatch.setattr(utils_mod.HttpClientPool, "get_client", staticmethod(lambda: FakeClient()))

    out = await chat_mod._handle_logistics_quote("báo giá...", "req-test")

    assert "?" not in out.replace("hoặc báo", "")  # không còn mã nháp "?" giả
    assert "Đã tạo nháp" not in out
    assert "chưa xác nhận" in out
