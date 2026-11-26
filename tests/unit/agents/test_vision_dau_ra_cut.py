"""
tests/unit/agents/test_vision_dau_ra_cut.py — đầu ra của model thị giác bị CẮT ở `max_tokens` không được vá thành số (R1).

VÌ SAO CÓ FILE NÀY
------------------
`VisionAgent._extract_json` chạy `repair_json` trên chữ model trả về. Model hết `max_tokens` giữa chừng thì chuỗi cụt, và
`repair_json` đóng ngoặc cho nó: `{"items": [...], "total": 5519` (tờ in 55192, cụt giữa số) thành một object hợp lệ có
`total = 5519`. Mọi phép kiểm nhất quán phía sau (`validate_invoice_total`, `freight_invoice.verify`) tính trên con số cụt đó, và
con số cụt trông như một lần đọc sai bình thường: không ai phân biệt được với lỗi đọc của model. Chỉ có `finish_reason` của server
(hoặc độ dài token ở đường trong tiến trình) nói được rằng nó cụt, nên phải chặn ở đó, trước khi vá.

Phạm vi: chỉ đường TRÍCH SỐ (`extract_invoice`, `extract_freight_invoice`). Chú thích ảnh và OCR chữ thô cụt thì phần đầu vẫn đọc được
và cụt là chuyện thường ở tờ dài, nên `analyze_image` mặc định giữ nguyên hành vi cũ.

Đường trong tiến trình (transformers) cần torch và model thật, chạy ở Colab: ở đây chỉ khoá phép suy `_bi_cat_cut`.
"""

from __future__ import annotations

import asyncio

import pytest
from json_repair import repair_json

from src.agents.vision import VisionAgent
from src.core.engine import ModelEngine, _bi_cat_cut
from tests.integration.runtime import test_engine_backend as teb

ANH = b"\x89PNG\r\n\x1a\n" + b"hoa-don-gia" * 20

# Tờ in tổng 55.192 đ; model bị cắt ngay giữa số tổng.
CUT_GIUA_SO = '{"items": [{"name": "Dầu nhớt", "price": 55192, "qty": 1}], "total": 5519'
TRON = '{"items": [{"name": "Dầu nhớt", "price": 55192, "qty": 1}], "total": 55192}'
CUOC_CUT = '{"carrier": "Nhà xe A", "charges": [{"description": "Cước", "unit_price": 1500000'


def _dung(monkeypatch, tmp_path, noi_dung: str, finish_reason: str | None):
    gia = teb._VllmGia(noi_dung=noi_dung, finish_reason=finish_reason)
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "SERVER")
    monkeypatch.setenv("VLLM_BASE_URL", gia.url)
    monkeypatch.setenv("VLLM_MODEL", "anser-v3")
    monkeypatch.setenv("VLLM_VISION_BASE_URL", gia.url + "/v1")
    monkeypatch.setenv("VLLM_VISION_MODEL", "anser-vision")
    anh = tmp_path / "hoa_don.png"
    anh.write_bytes(ANH)
    return VisionAgent(ModelEngine()), gia, str(anh)


@pytest.fixture(autouse=True)
def _don_singleton(monkeypatch):
    yield
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_chung_minh_repair_json_thuc_su_va_cut_thanh_so_sai():
    """Chốt chống xanh suông: nếu `repair_json` không vá cụt thành số thì các test dưới không chứng minh gì."""
    vá = repair_json(CUT_GIUA_SO, return_objects=True)
    assert isinstance(vá, dict) and vá["total"] == 5519, "đây chính là con số sai sẽ lọt vào sổ nếu không chặn"


def test_hoa_don_ban_le_cut_thi_loi_khong_ra_so(monkeypatch, tmp_path):
    ag, gia, anh = _dung(monkeypatch, tmp_path, CUT_GIUA_SO, "length")
    try:
        out = asyncio.run(ag.extract_invoice(anh))
    finally:
        gia.dong()
    assert "error" in out
    assert "total" not in out and "items" not in out, "không được lộ một phần nào của số đã cụt"
    assert "cụt" in out["error"]
    assert "5519" not in out["error"] and "Dầu nhớt" not in out["error"], "thông báo lỗi không mang chữ đọc từ ảnh"


def test_hoa_don_cuoc_cut_thi_loi_khong_ra_so(monkeypatch, tmp_path):
    ag, gia, anh = _dung(monkeypatch, tmp_path, CUOC_CUT, "length")
    try:
        out = asyncio.run(ag.extract_freight_invoice(anh))
    finally:
        gia.dong()
    assert "error" in out and "charges" not in out and "cụt" in out["error"]


def test_abort_giua_chung_cung_la_cut(monkeypatch, tmp_path):
    ag, gia, anh = _dung(monkeypatch, tmp_path, CUT_GIUA_SO, "abort")
    try:
        out = asyncio.run(ag.extract_invoice(anh))
    finally:
        gia.dong()
    assert "error" in out and "total" not in out


def test_model_tu_ket_thuc_thi_nhu_cu(monkeypatch, tmp_path):
    """Đối chứng: `finish_reason: stop` và JSON trọn thì ra đúng số in trên tờ. Không có ca này thì test chỉ chứng minh 'luôn từ chối'."""
    ag, gia, anh = _dung(monkeypatch, tmp_path, TRON, "stop")
    try:
        out = asyncio.run(ag.extract_invoice(anh))
    finally:
        gia.dong()
    assert out["total"] == 55192 and out["items"][0]["price"] == 55192


def test_server_khong_gui_finish_reason_thi_khong_chan(monkeypatch, tmp_path):
    """Không biết không phải là cụt: server khác không gửi `finish_reason` thì giữ hành vi cũ (vLLM thật luôn gửi)."""
    ag, gia, anh = _dung(monkeypatch, tmp_path, TRON, None)
    try:
        out = asyncio.run(ag.extract_invoice(anh))
    finally:
        gia.dong()
    assert out["total"] == 55192


def test_chu_thich_va_ocr_chu_tho_cut_van_tra_phan_dau(monkeypatch, tmp_path):
    """Phạm vi hẹp có chủ ý: không đọc số thì cụt vẫn dùng được phần đầu, `analyze_image` mặc định không đổi."""
    ag, gia, anh = _dung(monkeypatch, tmp_path, "Hoá đơn của cửa hàng Minh Phát, ngày 12 tháng", "length")
    try:
        mo_ta = asyncio.run(ag.analyze_image(anh, task_hint="caption"))
        ocr = asyncio.run(ag.analyze_image(anh, task_hint="ocr"))
    finally:
        gia.dong()
    assert mo_ta.startswith("Hoá đơn của cửa hàng") and not mo_ta.startswith("Error")
    assert ocr.startswith("Hoá đơn của cửa hàng") and not ocr.startswith("Error")


def test_cu_tren_duong_server_gui_dung_so_token_toi_da(monkeypatch, tmp_path):
    """Ngưỡng cụt tính theo `max_tokens` thật đã gửi lên server, nên thông báo nêu đúng số đó (1024 cho hoá đơn)."""
    ag, gia, anh = _dung(monkeypatch, tmp_path, CUT_GIUA_SO, "length")
    try:
        out = asyncio.run(ag.extract_invoice(anh))
    finally:
        gia.dong()
    _, than = gia.requests[0]
    assert than["max_tokens"] == 1024 and "1024" in out["error"]


# ---------------------------------------------------------------------------
# Đường trong tiến trình: suy ra từ độ dài
# ---------------------------------------------------------------------------

EOS = [151645, 151643]


@pytest.mark.parametrize("token_moi, toi_da, mong", [
    ([1, 2, 3, 4], 4, True),                  # đủ 4 token, token cuối không phải EOS: cụt
    ([1, 2, 3, 151645], 4, False),            # đủ 4 token nhưng token cuối là EOS: vừa kịp kết thúc
    ([1, 2, 3, 151643], 4, False),            # EOS thứ hai trong danh sách cũng tính
    ([1, 2, 3], 4, False),                    # chưa đủ: tự dừng
    ([], 4, False),                           # rỗng: không phải cụt, người đọc đã coi rỗng là không đọc được
    ([1, 2, 3, 4, 5], 4, True),               # vượt (không nên xảy ra) vẫn là cụt nếu không có EOS
])
def test_bi_cat_cut(token_moi, toi_da, mong):
    assert _bi_cat_cut(token_moi, toi_da, EOS) is mong


def test_bi_cat_cut_eos_none_khong_lam_no_va_khong_khop_nham():
    """`generation_config.eos_token_id` có thể là None: bỏ qua, không được coi `None` là một token để khớp."""
    assert _bi_cat_cut([1, 2, 3], 3, [None, None]) is True
    assert _bi_cat_cut([1, 2, 3], 3, [3, None]) is False
