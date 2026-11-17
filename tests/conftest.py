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
