"""
tests/conftest.py — cô lập bộ test khỏi biến môi trường của máy chạy.

Từ BR-03 (chu kỳ 01), `VLLM_BASE_URL` THẮNG `ENV=LOCAL` ở phía text: có biến đó
thì `ModelEngine` gọi vLLM server thật, ở mọi môi trường. Đó là chủ ý (rẽ theo
backend, không theo tên môi trường), nhưng nó có một hệ quả: máy dev nào đang
export `VLLM_BASE_URL` để thử với Colab sẽ thấy các test "mock" đi gọi mạng.

Nên mặc định gỡ hai biến đó cho MỌI test. Test nào cần đường server thì tự
`monkeypatch.setenv` — và như vậy đọc test là thấy ngay nó cần server.
"""

import os

import pytest

# Hằng số đọc env LÚC IMPORT (`serving.REPETITION_PENALTY_TU_DO`), nên phải gỡ
# ngay khi conftest nạp — trước mọi module `src` — chứ fixture thì đã muộn.
# Sự cố 29/10/2026: ô Colab đo repetition_penalty để lại `=1.0` trong phiên,
# pytest sau đó trượt 4 ca kiểm mặc định 1,25.
os.environ.pop("TEXT_REPETITION_PENALTY", None)
# Cùng lý do: `engine.TASK_REGISTRY` chọn Redis hay RAM LÚC IMPORT (#15). Bộ
# test chạy với RAM như ENV=LOCAL; test Redis tự dựng registry từ REDIS_TEST_URL.
os.environ.pop("REDIS_URL", None)


@pytest.fixture(autouse=True)
def _khong_mang_vllm_tu_may_chay_vao_test(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    # Cùng lý do cho đường vision qua HTTP (#14).
    monkeypatch.delenv("VLLM_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_VISION_MODEL", raising=False)


@pytest.fixture(autouse=True)
def _metrics_khong_ghi_file_that(monkeypatch, tmp_path):
    # `metrics.record()` mặc định ghi vào src/data/ai_metrics_log.jsonl — chạy
    # test là đổ lượt giả vào file đo thật (PCBoiz, #9). Mỗi test một file tạm,
    # và cửa sổ p95 của /health bắt đầu rỗng: lượt của test trước không được
    # làm test sau "đạt" hay "chưa đạt".
    from src.core import metrics
    monkeypatch.setattr(metrics, "METRICS_PATH", str(tmp_path / "ai_metrics_log.jsonl"))
    for ten in ("P95_CUA_SO", "P95_MAU_TOI_THIEU", "P95_MS_MOI_TOKEN", "P95_NGUONG_MS"):
        monkeypatch.delenv(ten, raising=False)
    metrics.dat_lai_cua_so_p95()


# ---------------------------------------------------------------------------
# Skip phải được KHAI (#29)
# ---------------------------------------------------------------------------
# Ba sự cố trong một tuần (09–10/11/2026), cùng một hình dạng: 46 ca kiểm token,
# 2 ca kiểm grammar và 1 ca `parametrize` trên danh sách rỗng ngừng chạy mà nhãn
# vẫn xanh, vì `pytest -q` không in lý do skip. Hai trong ba là cổng an toàn.
#
# Luật: trên CI, số ca skip của MỖI FILE phải khớp đúng con số khai dưới đây.
# Khai, không phải cấm: skip hợp lệ có thật. Lệch theo CẢ HAI chiều là đỏ:
#   - nhiều hơn: có test vừa ngừng chạy mà chưa ai quyết;
#   - ít hơn: lý do skip đã hết (ví dụ CI cài thêm gói), danh sách thành sai —
#     lần sau không ai tin nó nữa.
#
# Đếm THEO FILE chứ không theo tên test: đổi tên test không đỏ oan, mà vẫn đủ
# chỉ ra skip nằm ở đâu. Một `importorskip` ở đầu module bỏ qua CẢ FILE nhưng
# pytest chỉ báo MỘT ca skip — con số khai cho file đó là 1, không phải số test.
#
# Chỉ áp khi `KIEM_SKIP_DA_KHAI=1` (bước Pytest của CI đặt). Máy dev cài gói khác
# CI và thường không có Redis thật, nên số skip ở đó khác là bình thường. Muốn
# thử ở máy mình: dựng môi trường đúng như bước cài của ci.yml rồi đặt biến đó.
SKIP_DA_KHAI: dict[str, tuple[int, str]] = {
    "tests/test_agentic_plan.py": (
        2, "thiếu `xgrammar` (gói nặng, kéo torch) — xem requirements-dev.txt"),
    "tests/test_body_contract.py": (
        1, "CI không có repo Body bên cạnh; test này cần ANSER_BODY_DIR"),
    "tests/test_deploy_config.py": (
        2, "parametrize trên CHUA_NOI và ENV_MAU_NGOAI_COMPOSE, cả hai CỐ Ý rỗng; "
           "đã có test canh chiều ngược lại trong chính file đó"),
}

_skip_theo_file: dict[str, int] = {}
_file_da_chay: set[str] = set()
_loi_skip: list[str] = []


def _ten_file(nodeid: str) -> str:
    return nodeid.split("::", 1)[0].replace("\\", "/")


def _dang_kiem_skip() -> bool:
    return os.getenv("KIEM_SKIP_DA_KHAI", "").strip() == "1"


def pytest_collectreport(report):
    ten = _ten_file(report.nodeid)
    if not ten.endswith(".py"):
        return
    _file_da_chay.add(ten)
    # `importorskip` ở mức module: cả file bị bỏ qua lúc THU test.
    if report.skipped:
        _skip_theo_file[ten] = _skip_theo_file.get(ten, 0) + 1


def pytest_runtest_logreport(report):
    # Skip xảy ra ở pha setup (skipif, parametrize rỗng) hoặc call (pytest.skip
    # trong thân test, importorskip trong hàm). Mỗi test chỉ skip ở một pha.
    if report.skipped and not hasattr(report, "wasxfail"):
        ten = _ten_file(report.nodeid)
        _skip_theo_file[ten] = _skip_theo_file.get(ten, 0) + 1


def doi_chieu_skip(thuc_te: dict[str, int], da_chay: set[str],
                   khai: dict[str, tuple[int, str]]) -> list[str]:
    """Các dòng lệch giữa số skip thực tế và số đã khai. Rỗng là khớp.

    Chỉ xét file THỰC SỰ được chạy, để `pytest tests/test_x.py` có bật cổng
    không đỏ vì những file nằm ngoài lần chạy đó.
    """
    loi = []
    for ten in sorted(set(thuc_te) | set(khai)):
        if ten not in da_chay:
            continue
        co = thuc_te.get(ten, 0)
        mong = khai.get(ten, (0, ""))[0]
        if co > mong:
            loi.append(f"{ten}: {co} ca skip, khai {mong} — có test vừa ngừng chạy")
        elif co < mong:
            loi.append(f"{ten}: {co} ca skip, khai {mong} — lý do skip đã hết, "
                       f"sửa con số khai")
    return loi


def pytest_sessionfinish(session, exitstatus):
    if not _dang_kiem_skip():
        return
    _loi_skip[:] = doi_chieu_skip(_skip_theo_file, _file_da_chay, SKIP_DA_KHAI)
    if _loi_skip and session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    if not _loi_skip:
        return
    tr = terminalreporter
    tr.section("SKIP CHƯA KHAI (#29)", red=True)
    for dong in _loi_skip:
        tr.write_line(dong, red=True)
    tr.write_line(
        "Chạy `pytest -rs` để xem lý do từng ca. Skip hợp lệ thì khai vào "
        "SKIP_DA_KHAI trong tests/conftest.py, kèm lý do; không hợp lệ thì "
        "sửa cho test chạy lại."
    )
