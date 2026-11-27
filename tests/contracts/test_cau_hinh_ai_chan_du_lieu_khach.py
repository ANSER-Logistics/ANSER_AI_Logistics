"""
tests/contracts/test_cau_hinh_ai_chan_du_lieu_khach.py — cấu hình công cụ AI chặn đọc dữ liệu có thể là của khách (R2).

Lời dặn bằng văn xuôi ("đừng gửi src/data cho LLM") chỉ có tác dụng khi agent nhớ; chặn ở tầng công cụ thì luôn chạy
(`.claude/settings.json` cho Claude Code, `.geminiignore` cho Gemini CLI, `.graphifyignore` cho graphify). Ba file phải nói CÙNG
một danh sách, và danh sách phải còn nguyên: xoá nhầm một dòng thì không test nghiệp vụ nào đỏ, chỉ là một ngày nào đó agent đọc
tệp upload hay nhật ký hỏi đáp thật mà không ai thấy.

Chỉ kiểm hình dạng và độ khớp giữa các file; chưa có cách tự động kiểm Claude Code thật sự chặn (cần phiên mới nạp cấu hình).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Đường dẫn bắt buộc bị chặn đọc. Thêm đường dẫn mới thì thêm vào cả ba file và vào đây.
BAT_BUOC = [
    "src/data/*.png", "src/data/*.jpg", "src/data/*.jpeg", "src/data/*.pdf",
    "src/data/ai_metrics_log.jsonl",
    ".env", ".env.*", "deploy/.env",
]


def _deny_claude() -> list[str]:
    cau_hinh = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return cau_hinh["permissions"]["deny"]


def test_claude_settings_chan_du_cac_duong_dan_bat_buoc():
    deny = _deny_claude()
    assert all(d.startswith("Read(./") and d.endswith(")") for d in deny), deny
    da_chan = {d[len("Read(./"):-1] for d in deny}
    thieu = [p for p in BAT_BUOC if p not in da_chan]
    assert not thieu, f".claude/settings.json không chặn: {thieu}"


def test_geminiignore_khop_claude_settings():
    dong = {
        d.strip() for d in (ROOT / ".geminiignore").read_text(encoding="utf-8").splitlines()
        if d.strip() and not d.startswith("#")
    }
    thieu = [p for p in BAT_BUOC if p not in dong]
    assert not thieu, f".geminiignore không chặn: {thieu}"


def test_graphifyignore_van_loai_ca_thu_muc_du_lieu():
    """graphify loại hẳn `src/data/` (rộng hơn danh sách trên): giữ nguyên, kẻo bộ trích xuất LLM đọc được tệp upload."""
    dong = {d.strip() for d in (ROOT / ".graphifyignore").read_text(encoding="utf-8").splitlines()}
    assert "src/data/" in dong
