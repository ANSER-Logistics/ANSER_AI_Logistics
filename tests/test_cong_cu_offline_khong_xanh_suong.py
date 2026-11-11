"""
tests/test_cong_cu_offline_khong_xanh_suong.py — ba công cụ dọn dẹp, mỗi cái từng
cho một kết quả "sạch" mà thực ra là CHƯA LÀM GÌ.

  1. `soat_hinh_dang_tra_ve.py` ghi cứng đường dẫn một ổ đĩa. Chạy ở máy khác thì
     quét 0 file và in "tổng hàm có nhánh lệch hình dạng: 0". AGENTS §R1 chỉ
     người đọc dùng đúng lệnh này để soát.
  2. `merge_all.py` không thấy file nguồn nào thì ghi đè `train_retail_v2.jsonl`
     bằng file rỗng và thoát 0 ("✅ 0 mẫu").
  3. `.dockerignore` không tồn tại, nên `COPY src/` đưa `ai_metrics_log.jsonl`
     (nội dung các lượt hỏi đáp thật) vào ảnh Docker.

Cùng một hình dạng với ba sự cố "test skip im lặng" của tuần trước: một phép kiểm
báo xanh vì nó không có gì để kiểm.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_training import merge_all
from offline_training import soat_hinh_dang_tra_ve as soat

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. soát hình dạng trả về
# ---------------------------------------------------------------------------


def test_goc_quet_la_goc_repo_chu_khong_phai_mot_o_dia_cu_the():
    assert soat.GOC == REPO
    assert (soat.GOC / "src").is_dir() and (soat.GOC / "AGENTS.md").is_file()


def test_soat_that_su_quet_duoc_file_tren_repo_that(capsys):
    assert soat.main() == 0
    out = capsys.readouterr().out
    assert "đã quét" in out
    da_quet = int(out.rsplit("đã quét", 1)[1].split()[0])
    assert da_quet > 50, f"chỉ quét {da_quet} file — đường dẫn gốc sai?"


def test_quet_0_file_thi_khong_bao_sach(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(soat, "GOC", tmp_path)          # thư mục trống
    assert soat.main() == 2
    assert "chưa soát gì" in capsys.readouterr().err


def test_soat_bat_duoc_ham_tra_hai_hinh_dang(tmp_path):
    f = tmp_path / "m.py"
    f.write_text(
        "def h(x):\n"
        "    if x:\n"
        "        return {'a': 1, 'b': 2}\n"
        "    return {'a': 1}\n",
        encoding="utf-8",
    )
    ra = soat.soat_file(f)
    assert len(ra) == 1 and ra[0][0] == "h"
    assert ra[0][3] == [(4, ["b"])]


# ---------------------------------------------------------------------------
# 2. merge_all không ghi đè bằng file rỗng
# ---------------------------------------------------------------------------


def test_merge_all_khong_co_nguon_thi_khong_ghi_de_va_thoat_1(monkeypatch, tmp_path, capsys):
    out = tmp_path / "train_retail_v2.jsonl"
    out.write_text('{"messages": []}\n', encoding="utf-8")        # tập train cũ, đang có giá trị
    monkeypatch.setattr(merge_all, "DATA", tmp_path)
    monkeypatch.setattr(merge_all, "OUT", out)

    assert merge_all.main() == 1
    assert out.read_text(encoding="utf-8") == '{"messages": []}\n', "tập train cũ bị ghi đè"
    assert "KHÔNG ghi đè" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 3. .dockerignore
# ---------------------------------------------------------------------------


def _dong_dockerignore() -> list[str]:
    f = REPO / ".dockerignore"
    assert f.is_file(), "thiếu .dockerignore — ai_metrics_log.jsonl sẽ bị COPY vào ảnh Docker"
    return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


@pytest.mark.parametrize("phai_co", [".git", "_backups", ".env", "src/data/ai_metrics_log.jsonl"])
def test_dockerignore_loai_nhung_thu_nhay_cam(phai_co):
    assert phai_co in _dong_dockerignore()


@pytest.mark.parametrize("phai_vao_anh", ["requirements.txt", "src", "src/", "offline_training", "offline_training/", "src/data"])
def test_dockerignore_khong_loai_nhung_thu_dockerfile_can_copy(phai_vao_anh):
    """Dockerfile COPY ba thứ này. Loại nhầm một cái là image build ra thiếu mã."""
    assert phai_vao_anh not in _dong_dockerignore()


def test_dockerfile_van_chi_copy_nhung_thu_dockerignore_da_tinh_den():
    """Nếu ai thêm COPY mới (ví dụ `docs/`) mà quên .dockerignore thì test này đỏ."""
    copies = []
    for ln in (REPO / "deploy" / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if ln.strip().startswith("COPY "):
            copies += [p.rstrip("/") for p in ln.split()[1:-1]]
    loai = {ln.rstrip("/") for ln in _dong_dockerignore()}
    xung_dot = [c for c in copies if c in loai]
    assert not xung_dot, f"Dockerfile COPY thứ đang bị .dockerignore loại: {xung_dot}"
