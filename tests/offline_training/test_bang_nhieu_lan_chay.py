"""
tests/offline_training/test_bang_nhieu_lan_chay.py — bảng nhiều lần chạy cạnh nhau (v3, v4, mốc tham chiếu mạnh) cho #91.

Cái dễ sai ở đây là cái không báo lỗi: ghép theo vị trí thay vì theo mã câu, coi câu thiếu là câu sai, hoặc gọi một câu
"khoảng cách của model" trong khi mọi bản kể cả mốc mạnh đều sai nó (đề bài hỏng). Mỗi nhóm test dưới đây chặn một kiểu.
"""

from __future__ import annotations

import json

import pytest

from offline_training import bang_nhieu_lan_chay as b
from offline_training.bang_nhieu_lan_chay import LanChay, bang, main


def _muc(ids: list[str], per_row: list[bool], thu_lai: list[bool] | None = None) -> dict:
    m = {"row_ids": ids, "per_row": per_row}
    if thu_lai is not None:
        m["thu_lai"] = {"per_row": thu_lai}
    return m


def _lc(nhan: str, **sections) -> LanChay:
    return LanChay(nhan, f"model-{nhan}", "guided_json", sections)


IDS = ["A", "B", "C", "D"]


def test_gom_ba_loai_cau_va_chi_ra_cau_do_de_bai():
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, False]))
    v4 = _lc("v4", n8n=_muc(IDS, [True, False, False, False]))
    cl = _lc("claude", n8n=_muc(IDS, [True, True, False, False]))
    out = bang([v3, v4, cl], {"claude"})
    assert "Mọi lần chạy đều SAI (1): D" in out, "D không bản nào làm được: nghi đề bài"
    assert "Mốc tham chiếu đúng, MỌI bản local sai (0)" in out
    assert "v4 so với v3:  sửa được 0, LÀM HỎNG 2" in out
    assert "làm hỏng: B, C" in out
    assert "mốc tham chiếu làm được: 1/2 (B)" in out, "chỉ B là câu v4 hỏng mà Claude làm được; C thì Claude cũng sai"


def test_khoang_cach_that_cua_model_la_cau_mock_dung_ma_local_deu_sai():
    v3 = _lc("v3", n8n=_muc(IDS, [False, True, True, True]))
    v4 = _lc("v4", n8n=_muc(IDS, [False, True, True, True]))
    cl = _lc("claude", n8n=_muc(IDS, [True, True, True, True]))
    out = bang([v3, v4, cl], {"claude"})
    assert "Mốc tham chiếu đúng, MỌI bản local sai (1): A" in out


def test_ban_local_dung_ma_moc_sai_bi_goi_la_ca_la():
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, True]))
    v4 = _lc("v4", n8n=_muc(IDS, [True, True, True, True]))
    cl = _lc("claude", n8n=_muc(IDS, [True, True, True, False]))
    assert "Có bản local đúng, MỌI mốc tham chiếu sai (1): D" in bang([v3, v4, cl], {"claude"})


def test_ghep_theo_ma_cau_khong_theo_vi_tri():
    """Cùng ba câu nhưng sắp xếp lệch: ghép theo vị trí sẽ so câu A với câu B và cho kết quả sai mà trông bình thường."""
    v3 = _lc("v3", n8n=_muc(["A", "B", "C"], [True, False, True]))
    v4 = _lc("v4", n8n=_muc(["C", "B", "A"], [True, False, True]))      # A:T, B:F, C:T -> giống hệt v3
    out = bang([v3, v4], set())
    assert "sửa được 0, LÀM HỎNG 0" in out


def test_cau_chi_co_o_mot_ben_bi_bo_va_noi_ra_chu_khong_tinh_la_sai():
    v3 = _lc("v3", n8n=_muc(["A", "B", "C"], [True, True, True]))
    v4 = _lc("v4", n8n=_muc(["A", "B"], [True, True]))
    out = bang([v3, v4], set())
    assert "2 câu chung" in out and "có lần chạy mang câu riêng" in out
    assert "LÀM HỎNG 0" in out


def test_rang_buoc_khac_nhau_thi_canh_bao():
    v3 = _lc("v3", n8n=_muc(IDS, [True] * 4))
    ds = LanChay("deepseek", "deepseek-chat", "json_object", {"n8n": _muc(IDS, [True] * 4)})
    out = bang([v3, ds], {"deepseek"})
    assert "ràng buộc JSON KHÁC NHAU" in out


def test_sau_thu_lai_chi_ap_cho_lan_chay_co_muc_thu_lai_va_noi_ro():
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, False]))                          # không có thu_lai
    v4 = _lc("v4", n8n=_muc(IDS, [True, False, False, False], [True, True, False, False]))
    out = bang([v3, v4], set(), sau_thu_lai=True)
    assert "(sau một lần thử lại)" in out
    assert "lần chạy này không có mục thu_lai" in out, "v3 không có thu_lai: phải nói là đang dùng lần đầu"
    assert "v4 so với v3:  sửa được 0, LÀM HỎNG 1" in out, "v4 sau thử lại chỉ còn hỏng C"


def test_khong_co_sau_thu_lai_thi_dung_ket_qua_lan_dau():
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, False]))
    v4 = _lc("v4", n8n=_muc(IDS, [True, False, False, False], [True, True, True, True]))
    out = bang([v3, v4], set(), sau_thu_lai=False)
    assert "LÀM HỎNG 2" in out and "thử lại" not in out


def test_nhanh_chi_co_mot_lan_chay_thi_noi_khong_so_duoc():
    v3 = _lc("v3", n8n=_muc(IDS, [True] * 4), agent=_muc(["X"], [True]))
    v4 = _lc("v4", n8n=_muc(IDS, [True] * 4))
    assert "[agent] chỉ 1 lần chạy" in bang([v3, v4], set())


def test_nhan_tham_chieu_la_phai_co_trong_lan():
    with pytest.raises(ValueError, match="không có trong --lan"):
        bang([_lc("v3", n8n=_muc(IDS, [True] * 4))], {"claude"})


def test_file_hong_row_ids_va_per_row_lech_nhau_thi_nem():
    v3 = _lc("v3", n8n=_muc(["A", "B"], [True]))
    v4 = _lc("v4", n8n=_muc(["A", "B"], [True, True]))
    with pytest.raises(ValueError, match="per_row"):
        bang([v3, v4], set())


def test_dau_do_bat_duoc_viec_goi_de_loi_la_khoang_cach_model():
    """Chứng minh test không câm: câu D mọi bản sai KHÔNG được xuất hiện trong mục "khoảng cách thật"."""
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, False]))
    v4 = _lc("v4", n8n=_muc(IDS, [True, True, True, False]))
    cl = _lc("claude", n8n=_muc(IDS, [True, True, True, False]))
    out = bang([v3, v4, cl], {"claude"})
    assert "Mốc tham chiếu đúng, MỌI bản local sai (0)" in out
    assert "Mọi lần chạy đều SAI (1): D" in out


def test_main_doc_file_va_in_bang(tmp_path, capsys):
    def ghi(ten, per_row):
        p = tmp_path / f"{ten}.json"
        p.write_text(json.dumps({"model": ten, "rang_buoc": "guided_json",
                                 "sections": {"n8n": _muc(IDS, per_row)}}), encoding="utf-8")
        return f"{ten}={p}"

    assert main(["--lan", ghi("v3", [True, True, True, False]), "--lan", ghi("v4", [True, False, True, False]),
                 "--lan", ghi("claude", [True, True, True, True]), "--tham-chieu", "claude"]) == 0
    out = capsys.readouterr().out
    assert "[mốc tham chiếu]" in out and "v4 so với v3" in out


def test_nhan_trung_hoac_dang_sai_bi_tu_choi(tmp_path):
    with pytest.raises(SystemExit):
        main(["--lan", f"a={tmp_path}/x.json", "--lan", f"a={tmp_path}/y.json"])
    with pytest.raises(SystemExit):
        main(["--lan", "khong_co_dau_bang"])
    assert b._ma([]) == "(không có)"


# ---------------------------------------------------------------------------
# Bỏ câu nhãn sai khỏi điểm (#91: EX0034, EX0110) — bỏ khi ĐỌC, có lý do, nói rõ trong bảng
# ---------------------------------------------------------------------------

def test_bo_ma_bo_khoi_moi_lan_chay_va_noi_ro_trong_bang():
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, False]))
    v4 = _lc("v4", n8n=_muc(IDS, [True, False, False, False]))
    out = bang([v3, v4], set(), bo_ma={"C": "nhãn sai: tin nhắn có nơi đến"})
    assert "3 câu chung" in out
    assert "đã BỎ khỏi điểm: C (nhãn sai: tin nhắn có nơi đến)" in out
    assert "v4 so với v3:  sửa được 0, LÀM HỎNG 1" in out, "C bị bỏ nên v4 chỉ còn làm hỏng B"


def test_khong_bo_ma_thi_giu_nguyen_ket_qua_cu():
    v3 = _lc("v3", n8n=_muc(IDS, [True, True, True, False]))
    v4 = _lc("v4", n8n=_muc(IDS, [True, False, False, False]))
    assert bang([v3, v4], set()) == bang([v3, v4], set(), bo_ma={})
    assert "đã BỎ" not in bang([v3, v4], set())


def test_bo_ma_khong_co_trong_bo_de_thi_khong_noi_da_bo():
    v3 = _lc("v3", n8n=_muc(IDS, [True] * 4))
    v4 = _lc("v4", n8n=_muc(IDS, [True] * 4))
    assert "đã BỎ" not in bang([v3, v4], set(), bo_ma={"ZZZ": "không có trong đề"})


def test_doc_bo_ma_dung_dang_va_bat_buoc_co_ly_do(tmp_path):
    from offline_training.bang_nhieu_lan_chay import doc_bo_ma

    p = tmp_path / "bo.txt"
    p.write_text("# chú thích\n\nEX0034  # ship về HP nhưng nhãn null\nEX0110 # giao nội thành HN, nhãn null\n", encoding="utf-8")
    assert doc_bo_ma(str(p)) == {"EX0034": "ship về HP nhưng nhãn null", "EX0110": "giao nội thành HN, nhãn null"}
    p.write_text("EX0034\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="lý do"):
        doc_bo_ma(str(p))
    p.write_text("EX0034 #   \n", encoding="utf-8")
    with pytest.raises(SystemExit, match="lý do"):
        doc_bo_ma(str(p))
    with pytest.raises(SystemExit):
        doc_bo_ma(str(tmp_path / "khong_co.txt"))


def test_main_nhan_bo_ma_tep(tmp_path, capsys):
    def ghi(ten, per_row):
        f = tmp_path / f"{ten}.json"
        f.write_text(json.dumps({"model": ten, "rang_buoc": "guided_json", "sections": {"n8n": _muc(IDS, per_row)}}),
                     encoding="utf-8")
        return f"{ten}={f}"

    bo = tmp_path / "bo.txt"
    bo.write_text("D  # đề mơ hồ\n", encoding="utf-8")
    assert main(["--lan", ghi("v3", [True, True, True, False]), "--lan", ghi("v4", [True, False, True, False]),
                 "--bo-ma-tep", str(bo)]) == 0
    assert "đã BỎ khỏi điểm: D (đề mơ hồ)" in capsys.readouterr().out
