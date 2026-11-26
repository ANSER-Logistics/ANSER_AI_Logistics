"""
tests/unit/core/test_vllm_base_url_noi_bo.py — R2: `VLLM_BASE_URL` chỉ được trỏ vào host nội bộ.

VÌ SAO CÓ FILE NÀY
------------------
`VLLMServerClient` đọc `VLLM_BASE_URL` rồi gửi tới đó MỌI prompt — và prompt là
nơi dữ liệu khách nằm (hoá đơn, công nợ, bảng giá cước, biên lợi nhuận). Trước
đây không có gì kiểm giá trị đó: một biến môi trường đặt nhầm (hoặc đặt bởi
một người không hiểu R2) là đủ để đưa toàn bộ lưu lượng prompt tới
`https://api.<nhà-cung-cấp-bất-kỳ>.com/v1`, và Brain vẫn báo `status: ok`.

Bảng dưới đây là hợp đồng: host nào được, host nào bị từ chối. Các ca "lừa"
(`127.0.0.1.evil.com`, `localhost.evil.com`, `user@host`, số nguyên thay IP)
có mặt vì kiểm tra host bằng `startswith("127.")` hay `"localhost" in url` là cách
viết sai quen thuộc — mỗi ca ở đây là một đường thoát mà phép kiểm ngây thơ để lọt.

Không ca nào chạm mạng, không ca nào phân giải DNS: kiểm tra là phép đọc chuỗi.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
import socket

import pytest

from src.core.engine import CauHinhSai, ModelEngine
from src.core.serving import VLLMServerClient

GOC = pathlib.Path(__file__).resolve().parents[3]
COMPOSE = GOC / "deploy" / "docker-compose.yml"


# ---------------------------------------------------------------------------
# Được phép: loopback, RFC1918, tên không có dấu chấm
# ---------------------------------------------------------------------------

HOP_LE = [
    # loopback
    "http://localhost:8001",
    "http://LOCALHOST:8001",                   # không phân biệt hoa thường
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8001/v1",                # dạng AGENTS.md R5
    "http://127.255.255.254:8001",             # cả 127.0.0.0/8, không riêng .1
    "http://[::1]:8001",
    "http://[::1]:8001/v1",
    # RFC1918 — mép trong của từng dải
    "http://10.0.0.5:8001",
    "http://10.255.255.255:8001",
    "http://172.16.0.1:8001",
    "http://172.31.255.255:8001",
    "http://192.168.0.1:8001",
    "http://192.168.255.255:8001",
    # tên không có dấu chấm: tên service docker-compose
    "http://vllm-text:8001",                   # đúng giá trị trong deploy/docker-compose.yml
    "http://vllm-text:8001/v1/",
    "https://vllm-text",                       # https tới host nội bộ vẫn hợp lệ
    "http://vllm_text:8001",
    "http://vllm:8001",                        # giá trị tests/integration/runtime/test_serving.py đang dùng
    "http://h:8001",
    # IPv4 viết dưới dạng IPv6-mapped vẫn là địa chỉ nội bộ
    "http://[::ffff:127.0.0.1]:8001",
    "http://[::ffff:10.1.2.3]:8001",
    # có tiền tố đường dẫn (reverse proxy nội bộ) — host mới là thứ quyết định
    "http://vllm:8001/prefix",
    # `@` nằm Ở ĐƯỜNG DẪN thì không phải userinfo — host vẫn là `vllm`
    "http://vllm:8001/a@b",
    "http://" + "a" * 63 + ":8001",             # nhãn DNS dài đúng 63 ký tự
]


@pytest.mark.parametrize("url", HOP_LE)
def test_host_noi_bo_duoc_chap_nhan(url):
    c = VLLMServerClient(base_url=url)
    assert c.configured
    assert c.base_url and not c.base_url.endswith("/")
    assert not c.base_url.lower().endswith("/v1")      # chuẩn hoá cũ vẫn chạy


def test_chuan_hoa_cu_khong_doi():
    """Kiểm host KHÔNG được làm đổi giá trị `base_url` mà client dùng để gọi."""
    assert VLLMServerClient(base_url="http://127.0.0.1:8001/v1/").base_url == "http://127.0.0.1:8001"
    assert VLLMServerClient(base_url="  http://vllm-text:8001\n").base_url == "http://vllm-text:8001"


def test_rong_van_la_chua_cau_hinh_khong_phai_loi():
    """Không đặt biến = backend mock/in_process (chon_backend). Không được ném lỗi ở đây."""
    c = VLLMServerClient(base_url="")
    assert not c.configured


# ---------------------------------------------------------------------------
# Bị từ chối: host công cộng
# ---------------------------------------------------------------------------

HOST_CONG_CONG = [
    "https://api.openai.com/v1",
    "https://generativelanguage.googleapis.com",
    "http://example.com",
    "http://vllm.example.com:8001",
    "http://my-gpu.trycloudflare.com",
    # IP công cộng
    "http://8.8.8.8:8001",
    "http://1.1.1.1",
    "http://[2606:4700:4700::1111]:8001",
    # sát mép các dải được phép
    "http://11.0.0.1:8001",                    # ngay sau 10/8
    "http://9.255.255.255:8001",               # ngay trước 10/8
    "http://172.15.255.255:8001",              # ngay trước 172.16/12
    "http://172.32.0.1:8001",                  # ngay sau 172.16/12
    "http://192.167.255.255:8001",
    "http://192.169.0.1:8001",
    "http://126.255.255.255:8001",             # ngay trước 127/8
    "http://128.0.0.1:8001",                   # ngay sau 127/8
    # không phải "riêng" theo RFC1918 dù trông giống: link-local, CGNAT, 0.0.0.0
    "http://169.254.169.254",                  # metadata của đám mây
    "http://100.64.0.1:8001",
    "http://0.0.0.0:8001",
    "http://[fe80::1]:8001",
    "http://[::ffff:8.8.8.8]:8001",            # IPv6-mapped của IP công cộng
]


@pytest.mark.parametrize("url", HOST_CONG_CONG)
def test_host_cong_cong_bi_tu_choi_va_nen_ten_bien(url):
    with pytest.raises(CauHinhSai, match="VLLM_BASE_URL"):
        VLLMServerClient(base_url=url)


# ---------------------------------------------------------------------------
# Bị từ chối: host "lừa" — qua được phép kiểm chuỗi ngây thơ
# ---------------------------------------------------------------------------

HOST_LUA = [
    # tiền tố/hậu tố khớp tên được phép, nhưng miền thật là của người khác
    "http://127.0.0.1.evil.com:8001",
    "http://localhost.evil.com:8001",
    "http://10.0.0.1.evil.com",
    "http://192.168.1.1.nip.io",
    "http://vllm-text.evil.com:8001",
    "http://evil.com/127.0.0.1",
    "http://evil.com/localhost",
    # dấu chấm cuối: tên tuyệt đối, đã ra khỏi vùng tìm kiếm cục bộ
    "http://localhost.:8001",
    "http://vllm-text.:8001",
    # userinfo: phần TRƯỚC @ trông như host nội bộ, host thật nằm SAU
    "http://127.0.0.1@evil.com",
    "http://localhost:8001@evil.com",
    # fragment / query che host thật
    "http://evil.com#@127.0.0.1",
    "http://evil.com?@127.0.0.1",
    "http://evil.com?127.0.0.1",
    # dấu gạch ngược: urllib và trình duyệt/httpx đọc khác nhau
    "http://evil.com\\@127.0.0.1",
    "http://127.0.0.1\\@evil.com",
    # mã hoá phần trăm và Unicode để giấu dấu chấm
    "http://localhost%2eevil.com",
    "http://127.0.0.1%2eevil.com",
    "http://localhost。evil.com",          # dấu chấm kiểu CJK
    "http://127．0．0．1.evil.com",  # dấu chấm full-width
    "http://lоcalhost:8001",              # 'о' Cyrillic
    # số nguyên / thập lục / bát phân: hệ điều hành đọc thành IP, mà không có dấu chấm
    "http://2130706433",                       # = 127.0.0.1
    "http://16843009",                         # = 1.1.1.1  (IP CÔNG CỘNG, không dấu chấm)
    "http://0x7f000001",                       # = 127.0.0.1
    "http://0x01010101",                       # = 1.1.1.1
    "http://0177.0.0.1",
    "http://127.1",
    "http://0x7f.1",
    # nhãn số/hex không dấu chấm khác: hệ điều hành đọc thành địa chỉ
    "http://0",
    "http://0x",
    "http://256.1.1.1",                        # trông như IPv4, không phải IPv4
    "http://127.0.0.1.",                       # dấu chấm cuối
    "http://" + "a" * 64,                      # quá dài cho một nhãn DNS
    # IPv6 viết sai / có zone / không đóng ngoặc
    "http://[::1",
    "http://[::1]x",
    "http://[127.0.0.1]:8001",
    "http://[::1%eth0]:8001",
    "http://::1:8001",                         # IPv6 không ngoặc: nhiều dấu hai chấm
    "http://127.0.0.1:8001:9",
    # không có host
    "http://:8001",
    "http:///v1",
    "http://",
]


@pytest.mark.parametrize("url", HOST_LUA)
def test_host_lua_bi_tu_choi(url):
    with pytest.raises(CauHinhSai, match="VLLM_BASE_URL"):
        VLLMServerClient(base_url=url)


# ---------------------------------------------------------------------------
# Bộ đọc của chúng ta và bộ đọc của httpx phải thấy CÙNG một host
# ---------------------------------------------------------------------------
# Hướng nguy hiểm duy nhất: ta nhận URL mà httpx lại kết nối tới chỗ khác. Hai
# phép thử dưới đây chỉ nhìn đúng hướng đó. (httpx từ chối URL của ta là chuyện
# vô hại — không có kết nối nào được mở.)

def _host_httpx_thay(url: str) -> str | None:
    import httpx

    try:
        h = httpx.URL(url).host
    except httpx.InvalidURL:
        return None
    return f"[{h}]" if ":" in h else h


@pytest.mark.parametrize("url", HOP_LE)
def test_host_ta_nhan_cung_la_host_httpx_se_noi_toi(url):
    h = _host_httpx_thay(url)
    assert h is not None, f"httpx không đọc nổi URL mà ta nhận: {url}"
    VLLMServerClient(base_url=f"http://{h}")        # host httpx thấy cũng phải nội bộ


def test_fuzz_xac_dinh_khong_nhan_url_ma_httpx_noi_ra_ngoai():
    """
    Ghép ngẫu nhiên (hạt giống cố định) các mảnh hay dùng để lừa bộ đọc URL.
    Mọi chuỗi ta NHẬN mà httpx đọc được thì host httpx thấy (trên `base_url` đã
    chuẩn hoá — thứ client thật sự dùng) cũng phải qua kiểm.
    """
    import random

    manh = [
        "http://", "https://", "http:/", "127.0.0.1", "localhost", "vllm-text",
        "evil.com", "8.8.8.8", "10.0.0.1", ".", "..", ":", ":8001", "@", "/", "?",
        "#", "\\", "[", "]", "[::1]", "%2e", "%40", "%252e", "0x7f", "1", "0",
        "user:pw@", " ", "	",
    ]
    rng = random.Random(20261115)
    da_nhan = 0
    for _ in range(20000):
        url = "".join(rng.choice(manh) for _ in range(rng.randint(1, 7)))
        try:
            c = VLLMServerClient(base_url=url)
        except CauHinhSai:
            continue
        if not c.configured:             # chỉ toàn khoảng trắng = chưa cấu hình, không có kết nối nào
            continue
        da_nhan += 1
        h = _host_httpx_thay(c.base_url)     # đúng chuỗi client đưa cho httpx, không phải chuỗi thô
        if h is None:
            continue
        try:
            VLLMServerClient(base_url=f"http://{h}")
        except CauHinhSai as exc:        # pragma: no cover — chỉ chạy khi có lỗ hổng
            raise AssertionError(f"ta nhận {url!r} nhưng httpx nối tới {h!r}: {exc}") from exc
    assert da_nhan > 50, "fuzz không sinh đủ ca được nhận — phép thử không có tác dụng"


# ---------------------------------------------------------------------------
# user:pass@ — bí mật trong URL (R2b)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://user:S3cretPass@127.0.0.1:8001",
    "http://user:S3cretPass@vllm-text:8001",
    "http://S3cretPass@localhost:8001",
    "http://:S3cretPass@10.0.0.5:8001",
])
def test_user_pass_trong_url_bi_tu_choi_va_khong_lo_ra_thong_bao(url):
    """
    `base_url` được ghi vào log lúc dựng engine (`engine.py`) và nằm trong thông
    báo `BackendUnavailable`. URL mang mật khẩu thì mật khẩu theo vào log.
    Thông báo lỗi phải chỉ sang `VLLM_API_KEY` và KHÔNG được nhắc lại giá trị.
    """
    with pytest.raises(CauHinhSai) as exc:
        VLLMServerClient(base_url=url)
    thong_bao = str(exc.value)
    assert "VLLM_BASE_URL" in thong_bao
    assert "VLLM_API_KEY" in thong_bao
    assert "S3cretPass" not in thong_bao


# ---------------------------------------------------------------------------
# Scheme
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ftp://127.0.0.1:8001",
    "file:///etc/passwd",
    "gopher://localhost:8001",
    "ws://localhost:8001",
    "wss://vllm-text:8001",
    "unix:///var/run/vllm.sock",
    "javascript://localhost/%0aalert(1)",
    "HTTP-ish://localhost",
    # thiếu scheme: httpx cũng không dùng được các dạng này
    "127.0.0.1:8001",
    "localhost:8001",
    "vllm-text:8001",
    "//127.0.0.1:8001",
    "vllm-text",
])
def test_scheme_la_hoac_thieu_bi_tu_choi(url):
    with pytest.raises(CauHinhSai, match="VLLM_BASE_URL"):
        VLLMServerClient(base_url=url)


def test_scheme_http_https_khong_phan_biet_hoa_thuong():
    assert VLLMServerClient(base_url="HTTP://vllm-text:8001").configured
    assert VLLMServerClient(base_url="Https://vllm-text:8001").configured


# ---------------------------------------------------------------------------
# Cổng, ký tự lạ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:99999",
    "http://127.0.0.1:0",
    "http://127.0.0.1:",
    "http://127.0.0.1:" + "9" * 5000,          # không được làm `int()` nổ ValueError
    "http://127.0.0.1:abc",
    "http://127.0.0.1:-1",
    "http://127.0.0.1:80 01",
    "http://127.0.0.1 :8001",
    "http://127.0.0.1:80\n01",
    "http://127.0.0.1\t.evil.com",
    "http://127.0.0.1:8001/\x00",
])
def test_cong_sai_hoac_ky_tu_dieu_khien_bi_tu_choi(url):
    with pytest.raises(CauHinhSai, match="VLLM_BASE_URL"):
        VLLMServerClient(base_url=url)


# ---------------------------------------------------------------------------
# Thông báo lỗi: nêu tên biến, nêu host, KHÔNG nhắc lại phần còn lại của URL
# ---------------------------------------------------------------------------

def test_thong_bao_neu_host_va_khong_lo_query_hay_duong_dan():
    with pytest.raises(CauHinhSai) as exc:
        VLLMServerClient(base_url="https://api.nha-cung-cap.com/v1/KHOA-BI-MAT?key=TOKEN123")
    thong_bao = str(exc.value)
    assert "VLLM_BASE_URL" in thong_bao
    assert "api.nha-cung-cap.com" in thong_bao
    assert "TOKEN123" not in thong_bao and "KHOA-BI-MAT" not in thong_bao


def test_thong_bao_noi_ro_ly_do_la_du_lieu_khach():
    with pytest.raises(CauHinhSai) as exc:
        VLLMServerClient(base_url="https://api.nha-cung-cap.com")
    assert "R2" in str(exc.value)


def test_thong_bao_cat_host_dai_bat_thuong():
    host = "a" * 5000 + ".com"
    with pytest.raises(CauHinhSai) as exc:
        VLLMServerClient(base_url=f"http://{host}")
    assert len(str(exc.value)) < 1500


# ---------------------------------------------------------------------------
# Kiểm tra là phép đọc chuỗi: không phân giải DNS, không mở socket
# ---------------------------------------------------------------------------

def test_kiem_tra_khong_phan_giai_dns(monkeypatch):
    def _cam(*a, **k):
        raise AssertionError("kiểm host không được phân giải DNS")

    monkeypatch.setattr(socket, "getaddrinfo", _cam)
    monkeypatch.setattr(socket, "gethostbyname", _cam)
    assert VLLMServerClient(base_url="http://vllm-text:8001").configured
    with pytest.raises(CauHinhSai):
        VLLMServerClient(base_url="http://vllm.example.com:8001")


# ---------------------------------------------------------------------------
# Đường dùng thật: biến môi trường -> client -> engine -> /health
# ---------------------------------------------------------------------------

def test_bien_moi_truong_cong_cong_bi_chan_o_client(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "https://api.nha-cung-cap.com/v1")
    with pytest.raises(CauHinhSai, match="VLLM_BASE_URL"):
        VLLMServerClient()


def test_bien_moi_truong_noi_bo_van_chay(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm-text:8001")
    assert VLLMServerClient().base_url == "http://vllm-text:8001"


def test_engine_khong_dung_len_khi_url_cong_cong(monkeypatch):
    """
    `ENV=LOCAL` + `VLLM_BASE_URL` công cộng: engine phải từ chối dựng ngay lúc
    khởi tạo, không được lặng lẽ giữ một client trỏ ra ngoài rồi đợi request
    đầu tiên (lúc đó prompt của khách đã đi rồi).
    """
    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setenv("VLLM_BASE_URL", "https://api.nha-cung-cap.com/v1")
    try:
        with pytest.raises(CauHinhSai, match="VLLM_BASE_URL"):
            ModelEngine()
        assert ModelEngine._instance is None, "không được giữ instance hỏng"
    finally:
        monkeypatch.setattr(ModelEngine, "_instance", None)


def test_runtime_bao_loi_cau_hinh_o_engine_error_khong_sap(monkeypatch):
    """Cấu hình sai phải thấy được ở `/health.engine_error`, và Brain vẫn sống."""
    from src.api.dependencies import RuntimeState

    monkeypatch.setattr(ModelEngine, "_instance", None)
    monkeypatch.setenv("ENV", "SERVER")
    monkeypatch.setenv("VLLM_BASE_URL", "https://api.nha-cung-cap.com/v1")
    rs = RuntimeState()
    asyncio.run(rs.ensure_text_runtime())
    assert rs.engine is None
    assert "VLLM_BASE_URL" in (rs.engine_error or "")
    monkeypatch.setattr(ModelEngine, "_instance", None)


# ---------------------------------------------------------------------------
# Không chặn oan cấu hình đang dùng
# ---------------------------------------------------------------------------

def test_gia_tri_trong_compose_that_duoc_chap_nhan():
    """
    Đọc CHÍNH giá trị `VLLM_BASE_URL` trong deploy/docker-compose.yml. Ai đổi
    compose sang một tên miền công cộng sẽ làm test này đỏ, đúng lúc cần đỏ.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    gia_tri = re.findall(r"^\s+VLLM_BASE_URL:\s*(\S+)", text, re.M)
    assert gia_tri, "compose không đặt VLLM_BASE_URL cho brain"
    for url in gia_tri:
        assert VLLMServerClient(base_url=url).configured, url


def test_gia_tri_do_script_colab_dat_duoc_chap_nhan():
    """
    `offline_training/do_ngan_sach_ctx.py` trỏ Brain vào vLLM chạy trên CHÍNH máy
    Colab đó. Đọc URL gốc từ mã nguồn, không chép lại bằng tay.
    """
    nguon = (GOC / "offline_training" / "do_ngan_sach_ctx.py").read_text(encoding="utf-8")
    m = re.search(r'url_vllm\s*=\s*f"(http://[^"]+)"', nguon)
    assert m, "do_ngan_sach_ctx.py không còn gán url_vllm dạng f-string"
    url = m.group(1).replace("{CONG_VLLM}", "8001") + "/v1"   # script ghép thêm /v1 vào env
    assert VLLMServerClient(base_url=url).configured, url
