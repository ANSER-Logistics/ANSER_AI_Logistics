"""
tests/test_cong_cung.py — hook cổng cứng của Claude Code (`.claude/hooks/cong_cung.py`).

Chạy đúng như Claude Code chạy: tiến trình riêng, JSON vào stdin, mã thoát 2 là chặn. Repo git thử nằm ở thư mục tạm; bí mật giả ghép lúc chạy
(để nguyên chuỗi thì chính tệp này khớp bộ quét).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parents[2]
HOOK = GOC / ".claude" / "hooks" / "cong_cung.py"
GIA = "postgres" + "ql://admin:Xk9mQ2pLw@ep-x.neon.tech/db"


def _hook(cong_cu: str, vao: dict, cwd: Path = GOC) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_name": cong_cu, "tool_input": vao, "cwd": str(cwd)}),
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


def _git(repo: Path, *a: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *a], cwd=repo,
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """Repo có remote trần và một commit đã đẩy."""
    xa, r = tmp_path / "xa.git", tmp_path / "may"
    subprocess.run(["git", "init", "-q", "--bare", str(xa)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True, capture_output=True)
    (r / "a.txt").write_text("sach\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "dau")
    _git(r, "remote", "add", "origin", str(xa))
    _git(r, "push", "-q", "origin", "HEAD:main")
    _git(r, "fetch", "-q", "origin")
    return r


# ----------------------------------------------------------------------------- ghi tệp

@pytest.mark.parametrize("duong", ["src/data/x.jsonl", "src/data/docs/a.md", "src/core/../data/x.txt", ".env", "deploy/.env", ".env.local",
                                   str(GOC / "src" / "data" / "y.csv")])
@pytest.mark.parametrize("cong_cu", ["Write", "Edit"])
def test_chan_ghi_vao_du_lieu_khach_va_tep_env(duong, cong_cu):
    r = _hook(cong_cu, {"file_path": duong})
    assert r.returncode == 2, (duong, r.stderr)
    assert "CHẶN" in r.stderr


@pytest.mark.parametrize("duong", ["src/core/pricing.py", "deploy/.env.example", ".env.example", "src/database.py", "tests/test_x.py",
                                   str(Path(GOC.anchor) / "ngoai" / "src" / "data" / "z.txt")])
def test_khong_chan_oan_tep_binh_thuong(duong):
    r = _hook("Write", {"file_path": duong})
    assert r.returncode == 0, (duong, r.stderr)


def test_notebook_edit_cung_bi_kiem():
    assert _hook("NotebookEdit", {"notebook_path": "src/data/a.ipynb"}).returncode == 2


# ----------------------------------------------------------------------------- lệnh không phải git

@pytest.mark.parametrize("lenh", ["ls -la", "echo 'git commit'", "git status", "git log --oneline", "git diff --cached", "grep -r commit src"])
def test_lenh_khong_commit_khong_push_thi_cho_qua(lenh, tmp_path):
    assert _hook("Bash", {"command": lenh}, cwd=tmp_path).returncode == 0


def test_cong_cu_khac_thi_cho_qua():
    assert _hook("Read", {"file_path": "src/core/pricing.py"}).returncode == 0


# ----------------------------------------------------------------------------- commit

def test_commit_sach_thi_cho_qua(repo):
    (repo / "b.txt").write_text("khong co gi\n", encoding="utf-8")
    r = _hook("Bash", {"command": "git add -A && git commit -m x"}, cwd=repo)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("cong_cu", ["Bash", "PowerShell"])
def test_commit_co_bi_mat_trong_tep_chua_stage_thi_chan_va_khong_in_gia_tri(repo, cong_cu):
    (repo / "cau hinh.py").write_text(f"URL = '{GIA}'\n", encoding="utf-8")
    r = _hook(cong_cu, {"command": "git add -A; git commit -m x"}, cwd=repo)
    assert r.returncode == 2, r.stderr
    assert "cau hinh.py" in r.stderr
    assert "Xk9mQ2pLw" not in r.stderr + r.stdout and "admin:" not in r.stderr + r.stdout


@pytest.mark.parametrize("mau", ['cd "{r}" && git commit -m x', 'git -C "{r}" commit -m x'])
def test_theo_dung_repo_cua_lenh(repo, mau):
    (repo / "b.py").write_text(f"u = '{GIA}'\n", encoding="utf-8")
    r = _hook("Bash", {"command": mau.format(r=repo.as_posix())}, cwd=GOC)
    assert r.returncode == 2 and "b.py" in r.stderr, r.stderr


def test_cong_hong_thi_chan_khong_im_lang_cho_qua(tmp_path):
    r = _hook("Bash", {"command": "git commit -m x"}, cwd=tmp_path)          # không phải repo git
    assert r.returncode == 2 and "cổng cứng không chạy được" in r.stderr


# ----------------------------------------------------------------------------- push

def test_push_khong_co_gi_moi_thi_cho_qua(repo):
    assert _hook("Bash", {"command": "git push origin HEAD"}, cwd=repo).returncode == 0


def test_push_chan_bi_mat_trong_lich_su_chua_day_du_da_xoa_o_commit_sau(repo):
    (repo / "c.py").write_text(f"u = '{GIA}'\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lo")
    (repo / "c.py").write_text("u = ''\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "xoa")
    r = _hook("Bash", {"command": "git push -u origin nhanh"}, cwd=repo)
    assert r.returncode == 2 and "c.py" in r.stderr, r.stderr
    assert "Xk9mQ2pLw" not in r.stderr


def test_push_commit_sach_thi_cho_qua(repo):
    (repo / "d.txt").write_text("sach\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "sach")
    r = _hook("Bash", {"command": "git push"}, cwd=repo)
    assert r.returncode == 0, r.stderr


# ----------------------------------------------------------------------------- đăng ký

def test_settings_dang_ky_hook_cho_ca_lenh_va_ghi_tep():
    cau_hinh = json.loads((GOC / ".claude" / "settings.json").read_text(encoding="utf-8"))
    muc = {m["matcher"]: m["hooks"] for m in cau_hinh["hooks"]["PreToolUse"]}
    assert set(muc) == {"Bash|PowerShell", "Write|Edit|NotebookEdit"}
    for hooks in muc.values():
        assert any(".claude/hooks/cong_cung.py" in h["command"] for h in hooks)
    assert cau_hinh["permissions"]["deny"], "thêm hook không được làm mất danh sách chặn đọc"


# ----------------------------------------------------------------------------- đang gộp

def test_dang_gop_khong_bao_oan_tep_nguyen_van_tu_nhanh_kia_nhung_van_bat_tep_xung_dot_giai_tay(repo):
    """Kéo nhánh tính năng vào nhánh mình mang theo fixture của người khác (đã nằm trên remote): không được chặn. Chỗ mình tự giải xung đột thì vẫn quét."""
    _git(repo, "checkout", "-qb", "khac")
    (repo / "fixture.py").write_text(f"u = '{GIA}'\n", encoding="utf-8")        # fixture hợp lệ của người khác
    (repo / "a.txt").write_text("khac\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "khac")
    _git(repo, "checkout", "-q", "-")
    (repo / "a.txt").write_text("minh\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "minh")
    gop = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "--no-commit", "--no-ff", "khac"], cwd=repo, capture_output=True, text=True)    # xung đột ở a.txt
    assert (repo / ".git" / "MERGE_HEAD").is_file(), gop.stdout + gop.stderr                                          # phải thật sự đang gộp
    assert (repo / "fixture.py").is_file(), "fixture.py phải đến nguyên văn từ nhánh kia"
    r = _hook("Bash", {"command": "git commit -m gop"}, cwd=repo)
    assert r.returncode == 0, r.stderr
    (repo / "a.txt").write_text(f"giai tay {GIA}\n", encoding="utf-8")        # bí mật lọt vào chỗ giải tay
    r = _hook("Bash", {"command": "git commit -m gop"}, cwd=repo)
    assert r.returncode == 2 and "a.txt" in r.stderr, r.stderr
