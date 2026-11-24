"""
tests/test_benchmark_gop_vong.py — gom token nhiều vòng và kết luận ngữ cảnh mỗi server (notebook #176, review #254).

Lỗi đã gặp: notebook tính `max([...] or [0])`, nên server mà mọi lời gọi quá giờ hay thiếu `usage` ra "cần 0 token" và
bảng in "đủ". Ở đây khoá: không đo được là None và không kết luận; thiếu một phần là cận dưới, chỉ kết luận được THIẾU.
"""
from __future__ import annotations

from offline_training.benchmark_v3 import (
    ctx_can_server,
    gop_token_vong,
    ket_luan_ctx,
    tom_tat_token,
)


def _tt(prompt, max_tokens=1000, n_thieu=0, giay=1.0):
    nk = [{"prompt": prompt, "sinh": 10, "max_tokens": max_tokens, "giay": giay}]
    nk += [{"prompt": None, "sinh": None, "max_tokens": max_tokens, "giay": 300.0}] * n_thieu
    return tom_tat_token(nk)


def test_server_thieu_toan_bo_usage_thi_khong_do_duoc_va_khong_ket_luan():
    # Mọi vòng của mọi nhánh đều có lời gọi nhưng không usage: `tom_tat_token` trả None ở từng vòng.
    nhanh = [gop_token_vong([None, None]), gop_token_vong([None])]
    assert nhanh == [None, None]
    ctx = ctx_can_server(nhanh)
    assert ctx["ctx_can"] is None
    assert ket_luan_ctx(ctx, 8192) == "chưa kết luận: không đo được"
    assert "đủ" not in ket_luan_ctx(ctx, 8192)


def test_du_so_do_thi_ket_luan_du_hoac_thieu():
    ctx = ctx_can_server([gop_token_vong([_tt(3000), _tt(3500)]), gop_token_vong([_tt(2000, 4096)])])
    assert ctx == {"ctx_can": 6096, "can_duoi": False}
    assert ket_luan_ctx(ctx, 8192) == "đủ"
    assert ket_luan_ctx(ctx, 6000) == "THIẾU"


def test_thieu_usage_mot_phan_la_can_duoi_khong_duoc_noi_du():
    t = gop_token_vong([_tt(3000, n_thieu=2)])
    assert t["can_duoi"] and t["n_thieu_usage"] == 2 and t["ctx_can"] == 4000
    ctx = ctx_can_server([t])
    assert ctx["can_duoi"]
    assert ket_luan_ctx(ctx, 8192).startswith("chưa kết luận")
    # Cận dưới đã vượt trần thì chắc chắn thiếu.
    assert ket_luan_ctx(ctx, 3000) == "THIẾU"


def test_mot_vong_khong_do_duoc_la_can_duoi():
    t = gop_token_vong([_tt(3000), None])
    assert t["n_vong_khong_do"] == 1 and t["can_duoi"]


def test_mot_nhanh_khong_do_duoc_thi_server_la_can_duoi():
    ctx = ctx_can_server([gop_token_vong([_tt(3000)]), None])
    assert ctx == {"ctx_can": 4000, "can_duoi": True}
    assert ket_luan_ctx(ctx, 8192).startswith("chưa kết luận")


def test_gop_vong_lay_max_va_p95_vong_xau_nhat():
    t = gop_token_vong([_tt(3000, giay=2.0), _tt(5000, 512, giay=9.0)])
    assert (t["prompt_max"], t["max_tokens"], t["ctx_can"]) == (5000, 1000, 5512)
    assert t["giay_p95"] == 9.0 and t["n_goi"] == 2
