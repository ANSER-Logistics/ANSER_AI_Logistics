"""
tests/test_vision_server.py — Brain gọi vllm-vision qua HTTP (#14).

Đọc được biến `VLLM_VISION_BASE_URL` thì chưa chứng minh được gì. Test dưới
dựng server giả trên SOCKET THẬT (cùng `_VllmGia` với đường text) và đòi server
nhận được đúng ảnh, đúng model, đúng ràng buộc giải mã.
"""

from __future__ import annotations

import asyncio
import base64

import pytest

from src.core.engine import ModelEngine, chon_backend
from tests import test_engine_backend as teb

ANH = b"\x89PNG\r\n\x1a\n" + b"hoa-don-gia" * 20


@pytest.mark.parametrize("env,url", [
    ("LOCAL", ""), ("LOCAL", "http://t:8001"), ("GPU", ""), ("SERVER", "http://t:8001"),
])
def test_co_vision_url_thi_vision_di_server_o_moi_moi_truong(env, url):
    assert chon_backend(env, url, "http://v:8002")[1] == "server"


def test_khong_co_vision_url_thi_giu_nguyen_bang_cu():
    assert chon_backend("SERVER", "http://t:8001") == ("server", "none")
    assert chon_backend("SERVER", "http://t:8001", "  ") == ("server", "none")


@pytest.fixture
def engine_vision(monkeypatch, tmp_path):
    gia = teb._VllmGia(noi_dung='  {"items": [], "total": 0}  ')
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "SERVER")
    monkeypatch.setenv("VLLM_BASE_URL", gia.url)
    monkeypatch.setenv("VLLM_MODEL", "anser-v3")
    monkeypatch.setenv("VLLM_VISION_BASE_URL", gia.url + "/v1")
    monkeypatch.setenv("VLLM_VISION_MODEL", "anser-vision")
    anh = tmp_path / "hoa_don.png"
    anh.write_bytes(ANH)
    yield ModelEngine(), gia, anh
    gia.dong()
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_generate_vision_thuc_su_goi_toi_vllm_vision(engine_vision):
    eng, gia, anh = engine_vision
    assert eng.vision_backend == "server"
    schema = {"type": "object", "properties": {"items": {"type": "array"}}}

    out = asyncio.run(eng.generate_vision(str(anh), "Đọc hoá đơn này", json_schema=schema))

    assert out == '{"items": [], "total": 0}', "trả CHỮ đã strip, như đường trong tiến trình"
    assert gia.cac_duong() == ["/v1/chat/completions"], "server giả phải NHẬN được request"
    _, than = gia.requests[0]
    assert than["model"] == "anser-vision", "model vision, không phải model text"
    noi_dung = than["messages"][0]["content"]
    assert noi_dung[0]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(ANH).decode()), "ảnh đi nguyên vẹn"
    assert noi_dung[1] == {"type": "text", "text": "Đọc hoá đơn này"}
    assert than["guided_json"] == schema
    assert than["repetition_penalty"] == 1.0, "có grammar thì phải 1.0 (bẫy 3)"


def test_anh_vuot_tran_thi_khong_gui(engine_vision, monkeypatch):
    from src.core import config

    eng, gia, anh = engine_vision
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ValueError, match="MAX_UPLOAD_BYTES"):
        asyncio.run(eng.generate_vision(str(anh), "đọc"))
    assert gia.cac_duong() == [], "không được gửi ảnh quá trần lên server"


def test_khong_phai_anh_thi_khong_gui(engine_vision, tmp_path):
    eng, gia, _ = engine_vision
    tep = tmp_path / "hop_dong.pdf"
    tep.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="không phải ảnh"):
        asyncio.run(eng.generate_vision(str(tep), "đọc"))
    assert gia.cac_duong() == []


def test_health_env_server_bao_vision_server(engine_vision, monkeypatch):
    """Tiêu chí xong của #14: ENV=SERVER + VLLM_VISION_BASE_URL thì /health không
    còn khai `vision_backend: "none"`."""
    eng, _, _ = engine_vision
    body = teb._health_voi_engine(monkeypatch, eng)
    assert body["vision_backend"] == "server"
    assert body["vllm_vision_server"]["ok"] is True
    assert body["degraded"] is False


def test_vllm_vision_chet_thi_health_degraded(monkeypatch):
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_VISION_BASE_URL", "http://127.0.0.1:9")   # không ai nghe
    eng = ModelEngine()
    body = teb._health_voi_engine(monkeypatch, eng)
    assert body["vision_backend"] == "server"
    assert body["vllm_vision_server"]["ok"] is False
    assert body["degraded"] is True
    monkeypatch.setattr(ModelEngine, "_instance", None)
