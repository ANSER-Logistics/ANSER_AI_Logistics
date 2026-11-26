"""
tests/integration/runtime/test_dinh_tuyen_n8n.py — phương án hai server text (#176): workflow n8n sang server riêng (`VLLM_N8N_BASE_URL`), mọi tác vụ khác ở server chính.

Thành đo 24/11/2026 (#176): `anser-v3-awq` cho n8n (34/34 sau thử lại) và `anser-v5-awq` cho phần còn lại (bóc yêu cầu 91/98) cùng chạy trên một L4, VRAM 85,9%.
Phần mã ở đây chỉ chọn ĐỊA CHỈ và TÊN MODEL theo tác vụ (R5: đổi bằng `.env`, không sửa mã).

Như `test_engine_backend.py`: server giả là HTTP THẬT trên 127.0.0.1, và test đòi server NHẬN request. Không tiêm transport giả.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agents.coder import CoderAgent
from src.core import llm_suc_khoe
from src.core.engine import CauHinhSai, ModelEngine
from src.core.serving import BackendUnavailable
from tests.integration.runtime.test_engine_backend import _health_voi_engine, _VllmGia


@pytest.fixture
def hai_server():
    chinh, n8n = _VllmGia('{"kenh": "chinh"}'), _VllmGia('{"kenh": "n8n"}')
    yield chinh, n8n
    chinh.dong()
    n8n.dong()


@pytest.fixture
def vllm_gia():
    gia = _VllmGia()
    yield gia
    gia.dong()


@pytest.fixture
def engine_hai_server(monkeypatch, hai_server):
    chinh, n8n = hai_server
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", chinh.url + "/v1")
    monkeypatch.setenv("VLLM_MODEL", "anser-v5")
    monkeypatch.setenv("VLLM_N8N_BASE_URL", n8n.url + "/v1")
    monkeypatch.setenv("VLLM_N8N_MODEL", "anser-v3")
    eng = ModelEngine()
    yield eng
    monkeypatch.setattr(ModelEngine, "_instance", None)


def _chay(coro):
    return asyncio.run(coro)


def test_khong_dat_dia_chi_n8n_thi_moi_tac_vu_di_mot_server_nhu_cu(monkeypatch, vllm_gia):
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", vllm_gia.url + "/v1")
    monkeypatch.setenv("VLLM_MODEL", "anser-v5")
    monkeypatch.delenv("VLLM_N8N_BASE_URL", raising=False)
    eng = ModelEngine()
    assert eng.n8n_server is None and eng.n8n_guard is None
    _chay(eng.generate_chat("s", "u", tac_vu="n8n"))
    assert vllm_gia.cac_duong() == ["/v1/chat/completions"]
    assert vllm_gia.requests[0][1]["model"] == "anser-v5"
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_tac_vu_n8n_den_server_rieng_voi_dung_ten_model(engine_hai_server, hai_server):
    chinh, n8n = hai_server
    ra = _chay(engine_hai_server.generate_chat("s", "tạo workflow", json_schema={"type": "object"}, tac_vu="n8n"))
    assert ra.text == '{"kenh": "n8n"}'
    assert n8n.cac_duong() == ["/v1/chat/completions"] and chinh.cac_duong() == []
    assert n8n.requests[0][1]["model"] == "anser-v3"
    assert n8n.requests[0][1]["guided_json"] == {"type": "object"}, "grammar phải đi theo sang server n8n"


def test_tac_vu_khac_va_mac_dinh_den_server_chinh(engine_hai_server, hai_server):
    chinh, n8n = hai_server
    _chay(engine_hai_server.generate_chat("s", "u"))
    _chay(engine_hai_server.generate_chat("s", "u", tac_vu="chung"))
    assert chinh.cac_duong() == ["/v1/chat/completions"] * 2 and n8n.cac_duong() == []
    assert {r[1]["model"] for r in chinh.requests} == {"anser-v5"}


def test_coder_agent_sinh_workflow_di_kenh_n8n(engine_hai_server, hai_server):
    """Đúng người gọi: `CoderAgent.write_code` phải mang `tac_vu="n8n"`, nếu không cấu hình hai server không bao giờ được dùng."""
    chinh, n8n = hai_server
    _chay(CoderAgent(engine_hai_server, memory=None).write_code("báo cáo hằng ngày", "kế hoạch"))
    assert len(n8n.requests) == 1 and chinh.requests == []


def test_dia_chi_n8n_cong_cong_bi_tu_choi_va_noi_dung_ten_bien(monkeypatch, vllm_gia):
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", vllm_gia.url + "/v1")
    monkeypatch.setenv("VLLM_N8N_BASE_URL", "https://api.openai.com/v1")      # R2: chỉ host nội bộ
    with pytest.raises(CauHinhSai, match="VLLM_N8N_BASE_URL"):
        ModelEngine()
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_dat_dia_chi_n8n_ma_text_khong_di_qua_server_la_loi_cau_hinh(monkeypatch):
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.setenv("VLLM_N8N_BASE_URL", "http://127.0.0.1:8002/v1")
    with pytest.raises(CauHinhSai, match="VLLM_N8N_BASE_URL"):
        ModelEngine()
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_server_n8n_chet_khong_nuoi_mach_ngat_toan_cuc(monkeypatch, hai_server):
    """Server n8n chết thì chỉ sinh workflow hỏng; `/chat` thường (server chính còn sống) không được bị 503 `llm_unavailable`."""
    chinh, _ = hai_server
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", chinh.url + "/v1")
    monkeypatch.setenv("VLLM_N8N_BASE_URL", "http://127.0.0.1:9/v1")          # không ai nghe
    eng = ModelEngine()
    llm_suc_khoe.dat_lai()

    async def sinh_n8n():
        raise_ = None
        try:
            await eng.generate_chat("s", "u", tac_vu="n8n")
        except BackendUnavailable as e:
            raise_ = e
        assert raise_ is not None and getattr(raise_, "kenh", "") == "n8n"
        raise raise_

    for i in range(5):
        _chay(eng.background_worker(f"t{i}", sinh_n8n))
    assert llm_suc_khoe.trang_thai() == {"available": True, "consecutive_failures": 0}
    assert not llm_suc_khoe.dang_hong()
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_dieu_khien_am_server_chinh_chet_van_nuoi_mach_ngat(monkeypatch):
    """Không xanh suông: cùng kịch bản nhưng ở KÊNH CHUNG thì mạch ngắt phải mở như cũ."""
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.delenv("VLLM_N8N_BASE_URL", raising=False)
    eng = ModelEngine()
    llm_suc_khoe.dat_lai()

    async def sinh_chung():
        await eng.generate_chat("s", "u")

    for i in range(llm_suc_khoe.NGUONG_LOI):
        _chay(eng.background_worker(f"c{i}", sinh_chung))
    assert llm_suc_khoe.dang_hong()
    llm_suc_khoe.dat_lai()
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_health_bao_server_n8n_va_degraded_khi_no_chet(monkeypatch, hai_server):
    chinh, n8n = hai_server
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", chinh.url + "/v1")
    monkeypatch.setenv("VLLM_N8N_BASE_URL", n8n.url + "/v1")
    eng = ModelEngine()
    body = _health_voi_engine(monkeypatch, eng)
    assert body["vllm_n8n_server"]["ok"] is True
    assert "n8n" in body["load"]
    monkeypatch.setattr(ModelEngine, "_instance", None)

    monkeypatch.setenv("VLLM_N8N_BASE_URL", "http://127.0.0.1:9/v1")
    eng2 = ModelEngine()
    body2 = _health_voi_engine(monkeypatch, eng2)
    assert body2["vllm_n8n_server"]["ok"] is False
    assert body2["degraded"] is True
    monkeypatch.setattr(ModelEngine, "_instance", None)
