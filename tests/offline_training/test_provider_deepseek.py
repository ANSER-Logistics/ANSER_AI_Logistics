"""
tests/offline_training/test_provider_deepseek.py — provider `deepseek:` của benchmark (mốc tham chiếu cho #91).

VÌ SAO CÓ
---------
Chủ dự án cho phép gọi model mạnh bên ngoài làm mốc kiểm tra (17/11/2026). Provider này viết theo TÀI LIỆU công khai của
DeepSeek, chưa chạy trên API thật. Nên test ở đây khoá những thứ mà nếu sai thì phiên đo cho một bảng đẹp mà sai:

  1. Khoá API chỉ đọc từ biến môi trường, thiếu thì dừng (R2b), và không rò vào thông báo lỗi.
  2. Lược đồ đi vào prompt (JSON mode của DeepSeek không ép lược đồ), chữ "json" có mặt (tài liệu đòi), không đụng cuộc chat gốc.
  3. Nội dung trống ở chế độ JSON không bị tính là "model làm JSON hỏng" (tài liệu: nội dung không nhận ra là JSON bị thay bằng dấu cách).
  4. Địa chỉ là một hằng số, không đọc từ env: một biến địa chỉ là chỗ để gửi bộ đề đến nơi khác (R2).

Không cần mạng: phần dựng request là hàm thuần, phần gọi đi được thay bằng đồ giả.
"""

from __future__ import annotations

import json

import pytest

from offline_training import providers
from offline_training.dgen_common import DEEPSEEK_BASE_URL
from offline_training.providers import DeepSeek, dung_provider, payload_deepseek, tach_spec

CHAT = [
    {"role": "system", "content": "Bạn là trợ lý."},
    {"role": "user", "content": "Tạo luồng n8n."},
]
LUOC_DO = {"type": "object", "properties": {"ten": {"type": "string"}}, "required": ["ten"]}


@pytest.fixture
def co_khoa(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "khoa-gia-xyz")
    monkeypatch.delenv("BENCH_DEEPSEEK_EFFORT", raising=False)


# ---------------------------------------------------------------------------
# Phân giải --model
# ---------------------------------------------------------------------------

def test_tach_spec_deepseek_lay_ten_model():
    assert tach_spec("deepseek:deepseek-flash") == ("deepseek", "", "deepseek-flash")


def test_spec_deepseek_thieu_ten_model_bao_ngay():
    with pytest.raises(SystemExit, match="thiếu tên model"):
        tach_spec("deepseek:")


def test_dung_provider_tra_ve_ban_dung_deepseek(co_khoa):
    assert isinstance(dung_provider("deepseek:deepseek-flash"), DeepSeek)


# ---------------------------------------------------------------------------
# Khoá API (R2b)
# ---------------------------------------------------------------------------

def test_thieu_khoa_thi_dung_va_noi_cach_dat_khong_hardcode(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="DEEPSEEK_API_KEY") as e:
        DeepSeek("m", "deepseek:m")
    assert "R2b" in str(e.value)


def test_khoa_khong_xuat_hien_trong_loi_http(co_khoa, monkeypatch):
    class Hong:
        status_code = 401
        text = "unauthorized"

    monkeypatch.setattr("httpx.post", lambda *a, **k: Hong())
    with pytest.raises(RuntimeError) as e:
        DeepSeek("m", "deepseek:m")._mot_cau(CHAT, None, 64, 0.0)
    assert "khoa-gia-xyz" not in str(e.value)
    assert "401" in str(e.value)


def test_dia_chi_la_hang_so_khong_doc_tu_env(co_khoa, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://noi-khac.example")
    assert DeepSeek("m", "deepseek:m").base_url == DEEPSEEK_BASE_URL


def test_noi_ro_bo_de_di_ra_ngoai_theo_R2(co_khoa, capsys):
    DeepSeek("m", "deepseek:m")
    assert "R2" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Dựng request
# ---------------------------------------------------------------------------

def test_co_luoc_do_thi_json_mode_va_luoc_do_nam_trong_prompt():
    b = payload_deepseek("m", CHAT, LUOC_DO, 100, 0.0)
    assert b["response_format"] == {"type": "json_object"}
    he_thong = b["messages"][0]["content"]
    assert he_thong.startswith("Bạn là trợ lý.")
    assert "json" in he_thong.lower(), "tài liệu đòi chữ json trong prompt"
    assert json.dumps(LUOC_DO, ensure_ascii=False) in he_thong, "JSON mode không ép lược đồ: lược đồ phải đi bằng lời"
    assert b["messages"][1] == CHAT[1]


def test_khong_co_luoc_do_thi_khong_json_mode_va_khong_them_chi_dan():
    b = payload_deepseek("m", CHAT, None, 100, 0.0)
    assert "response_format" not in b
    assert b["messages"] == CHAT


def test_khong_co_tin_nhan_he_thong_thi_chen_mot_cai_len_dau():
    b = payload_deepseek("m", [CHAT[1]], LUOC_DO, 100, 0.0)
    assert b["messages"][0]["role"] == "system" and b["messages"][1] == CHAT[1]


def test_khong_dot_bien_cuoc_chat_cua_nguoi_goi():
    chat = [dict(m) for m in CHAT]
    payload_deepseek("m", chat, LUOC_DO, 100, 0.0)
    assert chat == CHAT


def test_suy_nghi_tat_mac_dinh_va_chinh_duoc():
    assert payload_deepseek("m", CHAT, None, 100, 0.0)["reasoning_effort"] == "none"
    assert payload_deepseek("m", CHAT, None, 100, 0.0, effort="high")["reasoning_effort"] == "high"
    assert "reasoning_effort" not in payload_deepseek("m", CHAT, None, 100, 0.0, effort="")


def test_khong_gui_phan_mo_rong_cua_vllm():
    b = payload_deepseek("m", CHAT, LUOC_DO, 100, 0.0)
    for khoa in ("guided_json", "chat_template_kwargs", "repetition_penalty"):
        assert khoa not in b


def test_tham_so_co_ban_duoc_chuyen_di():
    b = payload_deepseek("deepseek-flash", CHAT, None, 321, 0.3)
    assert (b["model"], b["max_tokens"], b["temperature"]) == ("deepseek-flash", 321, 0.3)


# ---------------------------------------------------------------------------
# Gọi đi (httpx thay bằng đồ giả)
# ---------------------------------------------------------------------------

class _Tra:
    def __init__(self, status=200, content="{}", finish="stop"):
        self.status_code = status
        self.text = "loi"
        self._d = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}

    def json(self):
        return self._d


def _gia_post(monkeypatch, *tra):
    cuoc = []
    dang = list(tra)

    def post(url, json=None, headers=None, timeout=None):
        cuoc.append((url, json, headers))
        return dang.pop(0)

    monkeypatch.setattr("httpx.post", post)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return cuoc


def test_goi_dung_url_va_gui_khoa_trong_header(co_khoa, monkeypatch):
    cuoc = _gia_post(monkeypatch, _Tra(content=' {"ten": "x"} '))
    text, ly_do = DeepSeek("m", "deepseek:m")._mot_cau(CHAT, LUOC_DO, 64, 0.0)
    assert (text, ly_do) == ('{"ten": "x"}', "stop")
    url, body, headers = cuoc[0]
    assert url == f"{DEEPSEEK_BASE_URL}/chat/completions"
    assert headers["Authorization"] == "Bearer khoa-gia-xyz"
    assert body["response_format"] == {"type": "json_object"}


def test_cham_tran_token_ra_length(co_khoa, monkeypatch):
    _gia_post(monkeypatch, _Tra(content='{"a": "dang do', finish="length"))
    assert DeepSeek("m", "deepseek:m")._mot_cau(CHAT, LUOC_DO, 8, 0.0)[1] == "length"


def test_noi_dung_trong_o_che_do_json_la_blank_khong_phai_json_hong(co_khoa, monkeypatch):
    _gia_post(monkeypatch, _Tra(content="      ", finish="stop"))
    assert DeepSeek("m", "deepseek:m")._mot_cau(CHAT, LUOC_DO, 64, 0.0) == ("", "blank")


def test_noi_dung_trong_khi_khong_che_do_json_van_la_stop(co_khoa, monkeypatch):
    _gia_post(monkeypatch, _Tra(content="", finish="stop"))
    assert DeepSeek("m", "deepseek:m")._mot_cau(CHAT, None, 64, 0.0) == ("", "stop")


def test_429_roi_thanh_cong_thi_thu_lai(co_khoa, monkeypatch):
    cuoc = _gia_post(monkeypatch, _Tra(status=429), _Tra(status=503), _Tra(content='{"ten": "x"}'))
    assert DeepSeek("m", "deepseek:m")._mot_cau(CHAT, LUOC_DO, 64, 0.0)[0] == '{"ten": "x"}'
    assert len(cuoc) == 3


def test_loi_5xx_lien_tuc_thi_noi_ro_chu_khong_lang_le(co_khoa, monkeypatch):
    _gia_post(monkeypatch, *[_Tra(status=500)] * 4)
    with pytest.raises(RuntimeError, match="500"):
        DeepSeek("m", "deepseek:m")._mot_cau(CHAT, None, 64, 0.0)


def test_qua_gio_ra_timeout_khong_dung_ca_phien(co_khoa, monkeypatch):
    import httpx

    def post(*a, **k):
        raise httpx.ReadTimeout("cham")

    monkeypatch.setattr("httpx.post", post)
    assert DeepSeek("m", "deepseek:m")._mot_cau(CHAT, None, 64, 0.0) == ("", "timeout")


def test_sinh_tra_hai_danh_sach_va_canh_bao_blank_va_ly_do_la(co_khoa, monkeypatch, capsys):
    _gia_post(monkeypatch, _Tra(content='{"ten": "x"}'), _Tra(content="  "), _Tra(content="x", finish="insufficient_system_resource"))
    monkeypatch.setattr(providers, "SONG_SONG", 1)
    texts, finishes = DeepSeek("m", "deepseek:m").sinh([CHAT] * 3, LUOC_DO, 64, 0.0)
    assert texts == ['{"ten": "x"}', "", "x"]
    assert finishes == ["stop", "blank", "insufficient_system_resource"]
    out = capsys.readouterr().out
    assert "NỘI DUNG TRỐNG" in out and "lý do dừng lạ" in out


def test_dau_do_bat_duoc_viec_thieu_chi_dan_luoc_do():
    """Chứng minh test không câm: bỏ lược đồ ra khỏi prompt thì kiểm tra "lược đồ đi bằng lời" phải đỏ."""
    b = payload_deepseek("m", CHAT, None, 100, 0.0)
    assert json.dumps(LUOC_DO, ensure_ascii=False) not in b["messages"][0]["content"]
