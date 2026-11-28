"""
tests/offline_training/test_benchmark_token.py — đếm token từng lời gọi để biết mỗi tác vụ cần `--max-model-len` bao nhiêu (#176).

VÌ SAO CÓ
---------
#176 chạy hai server vLLM (v3 cho n8n, v5 cho phần còn lại) trên một GPU, nên mỗi server có ngữ cảnh nhỏ hơn 32.768 của
compose. Issue đòi "đo độ dài prompt thực, đừng đoán". Test ở đây khoá ba điều mà nếu sai thì con số ra đẹp mà sai:
  1. Ngữ cảnh cần là `max(prompt + max_tokens)`, không phải `prompt + token đã sinh`: vLLM từ chối theo trần xin, không
     theo số đã sinh.
  2. Thiếu `usage` (server không phải vLLM, hay quá giờ) là KHÔNG ĐO ĐƯỢC (None), không phải 0 (R1: thiếu thì nói thiếu).
  3. Provider `openai:` ghi đúng số server trả, kể cả lời gọi quá giờ, và không đổi giá trị trả về của `_mot_cau`.
"""
from __future__ import annotations

import httpx
import pytest

from offline_training.benchmark_v3 import _phan_vi, tom_tat_token
from offline_training.providers import OpenAITuongThich

CHAT = [{"role": "user", "content": "Tạo luồng n8n."}]


def _goi(prompt, sinh, max_tokens=1000, giay=1.0):
    return {"prompt": prompt, "sinh": sinh, "max_tokens": max_tokens, "giay": giay, "ket_thuc": "stop"}


def test_ctx_can_tinh_theo_tran_xin_khong_theo_so_da_sinh():
    tt = tom_tat_token([_goi(3000, 200, 4096), _goi(5000, 900, 4096)])
    assert tt["ctx_can"] == 5000 + 4096
    assert tt["da_dung_max"] == 5000 + 900
    assert tt["prompt_max"] == 5000
    assert tt["max_tokens"] == 4096


def test_ctx_can_lay_max_tren_tung_loi_goi_khi_tran_khac_nhau():
    # Nhánh agent gọi `sinh` theo nhiều nhóm; trần có thể khác nhau giữa các nhóm. Cặp lớn nhất mới quyết định.
    tt = tom_tat_token([_goi(6000, 10, 64), _goi(2000, 10, 1024)])
    assert tt["ctx_can"] == 6064
    assert tt["max_tokens"] == 1024


def test_khong_co_loi_goi_hay_thieu_usage_thi_none_khong_phai_0():
    assert tom_tat_token([]) is None
    assert tom_tat_token([_goi(None, None)]) is None


def test_loi_goi_thieu_usage_duoc_dem_rieng():
    tt = tom_tat_token([_goi(100, 5), _goi(None, None, giay=300.0)])
    assert tt["n_goi"] == 2
    assert tt["n_thieu_usage"] == 1
    assert tt["ctx_can"] == 1100
    # Lời gọi quá giờ vẫn vào thời gian: p95 mà bỏ nó đi là giấu đúng ca chậm nhất.
    assert tt["giay_p95"] == 300.0


@pytest.mark.parametrize("mau, q, mong", [
    ([1.0], 0.95, 1.0),
    ([1.0, 2.0], 0.5, 1.0),
    (list(map(float, range(1, 21))), 0.95, 19.0),    # ceil(20×0,95)−1 = 18 → phần tử thứ 19
    (list(map(float, range(1, 35))), 0.95, 33.0),    # 34 câu n8n: ceil(32,3)−1 = 32 → 33
])
def test_phan_vi_nearest_rank_nhu_nguong_p95(mau, q, mong):
    from src.core.nguong_p95 import p95
    assert _phan_vi(mau, q) == mong
    if q == 0.95:
        assert _phan_vi(mau, q) == p95(mau)


class _Tra:
    def __init__(self, du_lieu, status=200):
        self._du_lieu = du_lieu
        self.status_code = status
        self.text = ""

    def json(self):
        return self._du_lieu


def test_provider_openai_ghi_usage_cua_server(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Tra({
        "choices": [{"message": {"content": " {} "}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 4321, "completion_tokens": 77},
    }))
    nha = OpenAITuongThich("http://127.0.0.1:8001/v1", "anser-v3", "openai:x")
    assert nha._mot_cau(CHAT, None, 512, 0.0) == ("{}", "length")
    (d,) = nha.nhat_ky
    assert (d["prompt"], d["sinh"], d["max_tokens"], d["ket_thuc"]) == (4321, 77, 512, "length")
    assert d["giay"] >= 0


def test_provider_openai_server_khong_tra_usage_thi_ghi_none(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Tra({
        "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
    }))
    nha = OpenAITuongThich("http://127.0.0.1:8001/v1", "m", "openai:x")
    nha._mot_cau(CHAT, None, 64, 0.0)
    assert nha.nhat_ky[0]["prompt"] is None
    assert tom_tat_token(nha.nhat_ky) is None


def test_provider_openai_qua_gio_van_ghi_mot_dong(monkeypatch):
    def qua_gio(*a, **k):
        raise httpx.ReadTimeout("chậm")
    monkeypatch.setattr("httpx.post", qua_gio)
    nha = OpenAITuongThich("http://127.0.0.1:8001/v1", "m", "openai:x")
    assert nha._mot_cau(CHAT, None, 64, 0.0) == ("", "timeout")
    assert nha.nhat_ky[0]["ket_thuc"] == "timeout"
    assert nha.nhat_ky[0]["prompt"] is None


def test_sinh_cong_don_nhat_ky_theo_thu_tu_moi_loi_goi(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Tra({
        "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1},
    }))
    nha = OpenAITuongThich("http://127.0.0.1:8001/v1", "m", "openai:x")
    nha.sinh([CHAT, CHAT, CHAT], None, max_tokens=8, temperature=0.0)
    moc = len(nha.nhat_ky)
    nha.sinh([CHAT], None, max_tokens=16, temperature=0.0)
    assert moc == 3
    # Cắt theo mốc là cách `benchmark_v3` tách từng nhánh.
    assert tom_tat_token(nha.nhat_ky[moc:])["ctx_can"] == 26
