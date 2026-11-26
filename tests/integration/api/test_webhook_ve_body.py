"""
tests/integration/api/test_webhook_ve_body.py — gửi kết quả về Body: kiểm trạng thái và thử lại (SRS §7.3, "callback về Body
chỉ ghi log khi thất bại").

Trước đây là MỘT lần `client.post` rồi log "Webhook dispatched". Hai lỗi câm:
  1. `httpx` không ném khi Body trả 401 hay 500: mọi phản hồi đều bị log là "đã gửi".
  2. Body khởi động lại thoáng qua thì lần gửi duy nhất mất kết quả.

Test dùng client giả có kịch bản và thay `_ngu` để không đợi thật. Không mạng, không GPU.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from src.api.routes import chat as chat_mod

URL = "http://body.test/api/callback"
KET_QUA_BI_MAT = "Tổng công nợ của khách Thử Nghiệm 01 là 123.456.789 đồng"
PAYLOAD = {"task_id": "t1", "result": KET_QUA_BI_MAT}


class Resp:
    def __init__(self, code: int):
        self.status_code = code


class KichBan:
    """Client giả: mỗi lần `post` lấy một bước kịch bản (mã trạng thái hoặc một ngoại lệ)."""

    def __init__(self, *buoc):
        self.buoc = list(buoc)
        self.so_lan = 0

    async def post(self, url, json=None, headers=None):
        self.so_lan += 1
        b = self.buoc.pop(0) if len(self.buoc) > 1 else self.buoc[0]
        if isinstance(b, Exception):
            raise b
        return Resp(b)


@pytest.fixture
def khong_doi(monkeypatch):
    cho: list[float] = []

    async def _ngu(giay):
        cho.append(giay)

    monkeypatch.setattr(chat_mod, "_ngu", _ngu)
    return cho


def _chay(client):
    async def lam():
        ok = await chat_mod._gui_webhook(client, URL, PAYLOAD, {"X-Task-ID": "t1"}, "t1")
        # đợi các lần thử lại ở nền (nếu có) xong, để test xác nhận được kết quả cuối
        if chat_mod._WEBHOOK_NEN:
            await asyncio.gather(*list(chat_mod._WEBHOOK_NEN))
        return ok
    return asyncio.run(lam())


def test_gui_duoc_ngay_lan_dau_thi_khong_thu_lai_va_khong_doi(khong_doi):
    c = KichBan(200)
    assert _chay(c) is True and c.so_lan == 1 and khong_doi == []


def test_coi_moi_ma_duoi_400_la_thanh_cong():
    for ma in (200, 201, 202, 204, 301):
        assert asyncio.run(chat_mod._gui_mot_lan(KichBan(ma), URL, {}, {}))[0] is True


@pytest.mark.parametrize("ma", [401, 403, 404, 422])
def test_body_tu_choi_4xx_thi_khong_thu_lai_va_khong_bao_da_gui(khong_doi, caplog, ma):
    """Bản cũ log 'dispatched' cho cả 401. Giờ: một lần, log ERROR, không thử lại, không đợi."""
    caplog.set_level(logging.INFO, logger="projecta.api.chat")
    c = KichBan(ma)
    assert _chay(c) is False
    assert c.so_lan == 1 and khong_doi == []
    chu = " ".join(r.getMessage() for r in caplog.records)
    assert "dispatched" not in chu and f"HTTP {ma}" in chu and "t1" in chu


@pytest.mark.parametrize("ma", [408, 429, 500, 502, 503])
def test_loi_tam_thoi_thu_lai_roi_thanh_cong(khong_doi, ma):
    c = KichBan(ma, ma, 200)
    assert _chay(c) is False, "trả kết quả của LẦN ĐẦU: lần đầu chưa tới Body"
    assert c.so_lan == 3, "lần đầu + hai lần thử lại, lần thứ ba tới nơi"
    assert khong_doi == [1.0, 4.0]


def test_loi_mang_cung_la_tam_thoi(khong_doi):
    c = KichBan(httpx.ConnectError("Body đang khởi động"), 200)
    assert _chay(c) is False and c.so_lan == 2 and khong_doi == [1.0]


def test_thu_het_so_lan_van_hong_thi_dung_va_log_error_co_cach_lay_ket_qua(khong_doi, caplog):
    caplog.set_level(logging.INFO, logger="projecta.api.chat")
    c = KichBan(503)
    assert _chay(c) is False
    assert c.so_lan == 3, "lần đầu + đúng hai lần thử lại, không hơn"
    loi = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(loi) == 1
    assert "GET /api/v1/task/t1" in loi[0].getMessage(), "log phải nói cách lấy kết quả khi webhook mất"


def test_dang_thu_lai_ma_gap_4xx_thi_dung_ngay(khong_doi):
    c = KichBan(503, 401)
    _chay(c)
    assert c.so_lan == 2 and khong_doi == [1.0], "401 sau lần lỗi tạm: không thử thêm"


def test_khong_bao_gio_ghi_noi_dung_tra_loi_vao_log(khong_doi, caplog):
    """Payload là câu trả lời cho khách (có số công nợ): log là nơi dữ liệu nằm lại."""
    caplog.set_level(logging.DEBUG)
    for kich_ban in (KichBan(200), KichBan(401), KichBan(503), KichBan(httpx.ReadTimeout("x"), 500, 500)):
        _chay(kich_ban)
    toan = " ".join(r.getMessage() for r in caplog.records)
    assert KET_QUA_BI_MAT not in toan and "123.456.789" not in toan


def test_khong_nem_ngoai_le_ra_ngoai_du_client_hong_theo_cach_la(khong_doi):
    class Hong:
        async def post(self, *a, **k):
            raise RuntimeError("lỗi lạ")

    async def lam():
        return await chat_mod._gui_webhook(Hong(), URL, PAYLOAD, {}, "t1")

    assert asyncio.run(lam()) is False
