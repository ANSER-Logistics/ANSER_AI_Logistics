"""
tests/offline_training/test_script_do_dau_cuoi.py — hai script đo đầu cuối hỏi đúng cách (#259).

Lượt chạy thật #257 (Colab L4, 24/11/2026) báo trượt sai lý do:
  1. `benchmark_integration.py` gửi `user_id: 1` mà không gửi `X-User-Id` khi hỏi kết quả task, nên
     `GET /api/v1/task/{id}` trả 404 và mọi ca thành [TIMEOUT].
  2. Câu đo không nói đủ dữ kiện nên chốt đầu vào HỎI LẠI đúng thiết kế (T5: giá đã gồm VAT chưa;
     hoá đơn của `chay_thu_live`: 8% hay 10% cho cước vận tải), trong khi ca đó đo đường tool chạy.
Test ở đây khoá cả hai: header khớp người hỏi, và câu đo đi qua `chot_dau_vao` THẬT với lý do "ok".
"""
from __future__ import annotations

import asyncio

import httpx

from offline_training import benchmark_integration as bi
from offline_training import chay_thu_live as live
from src.core.doc_dau_vao import chot_dau_vao


def _client(xu_ly):
    return httpx.AsyncClient(transport=httpx.MockTransport(xu_ly), headers=bi.HEADERS)


def test_hoi_ket_qua_task_gui_x_user_id_khop_user_id(monkeypatch):
    monkeypatch.setattr(bi, "POLL_GIAY", 0)
    thay: dict = {}

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            import json
            thay["user_id"] = json.loads(req.content)["user_id"]
            return httpx.Response(200, json={"task_id": "t1", "status": "processing"})
        thay["header"] = req.headers.get("X-User-Id")
        if req.headers.get("X-User-Id") != str(thay["user_id"]):
            return httpx.Response(404, json={"detail": "Task not found"})
        return httpx.Response(200, json={"status": "completed", "result": {"answer": "xong"}})

    async def chay():
        async with _client(xu_ly) as c:
            return await bi.ask(c, "câu hỏi")

    tra_loi, _ = asyncio.run(chay())
    assert tra_loi == "xong"
    assert thay["header"] == str(thay["user_id"]) == str(bi.NGUOI_HOI)


def test_404_khi_hoi_task_bao_ngay_khong_cho_het_poll(monkeypatch):
    monkeypatch.setattr(bi, "POLL_GIAY", 0)
    goi = {"get": 0}

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(200, json={"task_id": "t1", "status": "processing"})
        goi["get"] += 1
        return httpx.Response(404, json={"detail": "Task not found"})

    async def chay():
        async with _client(xu_ly) as c:
            return await bi.ask(c, "câu hỏi")

    tra_loi, _ = asyncio.run(chay())
    assert tra_loi.startswith("[404]") and "X-User-Id" in tra_loi
    assert goi["get"] == 1


def _ca(ma):
    return next(t for t in bi.TESTS if t["id"] == ma)


def test_t5_du_du_kien_de_tinh_khong_hoi_lai():
    cau = _ca("T5")["prompt"]
    # Tham số như model điền cho `vat`; thuế suất và cơ sở giá do MÃ đặt theo câu.
    args, hoi, ly_do = chot_dau_vao("vat", {"items": [{"name": "Đơn hàng", "price": 3500000, "qty": 1}]}, cau)
    assert (hoi, ly_do) == (None, "ok")
    assert args["prices_include_vat"] is False
    assert args["items"][0]["is_reduced_vat"] is True     # "thuế GTGT 8%" trong câu


def test_t5_cau_cu_thi_hoi_lai_co_so_gia():
    """Đối chứng: câu trước #259 bị hỏi lại đúng như lượt chạy thật thấy (lý do `thue`)."""
    cau = "Đơn hàng 3 triệu 500 nghìn, thuế GTGT 8% thì phải nộp bao nhiêu tiền thuế?"
    _, hoi, ly_do = chot_dau_vao("vat", {"items": [{"name": "Đơn hàng", "price": 3500000, "qty": 1}]}, cau)
    assert ly_do == "thue" and hoi


def test_hoa_don_chay_thu_live_chay_duoc_tool_vat():
    args, hoi, ly_do = chot_dau_vao("vat", {"stated_total": 6500000}, live.HOA_DON)
    assert (hoi, ly_do) == (None, "ok")
    assert all(it["is_reduced_vat"] is False for it in args["items"])   # "thuế suất 10%"


def test_hoa_don_cu_khong_noi_thue_suat_thi_hoi_8_hay_10():
    """Đối chứng: câu trước #259 rơi vào luật 3 (cước vận tải được giảm, câu không nói mức)."""
    cu = live.HOA_DON.replace(", thuế suất 10%", "")
    assert cu != live.HOA_DON
    _, hoi, ly_do = chot_dau_vao("vat", {"stated_total": 6500000}, cu)
    assert ly_do == "thue_suat" and "8%" in hoi
