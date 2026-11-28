"""
tests/test_cong_cung.py — hook cổng cứng của Claude Code (`.claude/hooks/cong_cung.py`).

Chạy đúng như Claude Code chạy: tiến trình riêng, JSON vào stdin, mã thoát 2 là chặn. Repo git thử nằm ở thư mục tạm; bí mật giả ghép lúc chạy
(để nguyên chuỗi thì chính tệp này khớp bộ quét).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
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


# ----------------------------------------------------------------------------- review của Dgsonn và wikiepeidia (PR #268)

def _nap_hook():
    spec = importlib.util.spec_from_file_location("cong_cung_thu", HOOK)
    mo_dun = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mo_dun)
    return mo_dun


def test_dau_vao_khong_phai_json_thi_chan_khong_cho_qua():
    """Không đọc được lời gọi nghĩa là không biết nó là gì: cổng hỏng thì CHẶN (trước đây `return 0`)."""
    r = subprocess.run([sys.executable, str(HOOK)], input="khong phai json", capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 2 and "CHẶN" in r.stderr


def test_dau_vao_json_nhung_khong_phai_dict_thi_khong_no_va_cho_qua():
    r = subprocess.run([sys.executable, str(HOOK)], input="[1, 2]", capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr


def test_loi_bat_ngo_trong_chinh_hook_doi_thanh_ma_2(monkeypatch, capsys):
    """Claude Code coi mã thoát 1 (traceback) là KHÔNG chặn; hook tự đổi lỗi bất ngờ thành 2."""
    import io

    hook = _nap_hook()
    monkeypatch.setattr(hook, "kiem", lambda d: (_ for _ in ()).throw(KeyError("x")))
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_name": "Bash"}'))
    assert hook.main() == 2
    assert "KeyError" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("ruff") is None and subprocess.run([sys.executable, "-m", "ruff", "--version"], capture_output=True).returncode != 0,
                    reason="cần ruff")
def test_tom_tat_ruff_chi_co_vi_tri_va_ma_loi_khong_chep_dong_ma(tmp_path):
    """Đầu ra hook đi vào nhật ký trò chuyện; dòng mã vừa gõ có thể chứa bí mật. Chuỗi hư cấu trong dòng mã và trong thông điệp lỗi không được xuất hiện."""
    canary = "SYNTHETIC_CANARY_9F3A7"
    f = tmp_path / "x.py"
    f.write_text(f"import {canary}\nkhoa = '{canary}'\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--output-format=json", "--no-cache", "--isolated", str(f)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1 and canary in r.stdout, "điều kiện thử: ruff phải thật sự nhắc tới chuỗi hư cấu trong kết quả thô"
    tom_tat = _nap_hook()._tom_tat_ruff(r.stdout, tmp_path)
    assert canary not in tom_tat
    assert "x.py:1:" in tom_tat and "F401" in tom_tat


def test_tom_tat_ruff_loi_cu_phap_khong_co_ma_va_ket_qua_hong():
    hook = _nap_hook()
    cu_phap = json.dumps([{"code": None, "message": "SyntaxError: ...", "filename": str(GOC / "a.py"), "location": {"row": 3, "column": 5}}])
    assert hook._tom_tat_ruff(cu_phap, GOC) == "a.py:3:5 lỗi cú pháp"
    assert "không đọc được" in hook._tom_tat_ruff("rác", GOC)
    assert "không có chi tiết" in hook._tom_tat_ruff("[]", GOC)
    nhieu = json.dumps([{"code": "F401", "filename": str(GOC / "a.py"), "location": {"row": i, "column": 1}} for i in range(1, 21)])
    assert "(+5 chỗ nữa)" in hook._tom_tat_ruff(nhieu, GOC)


def _bi_mat_tren_nhanh_khac(repo: Path) -> None:
    """Một commit có bí mật nằm trên nhánh `khac`; HEAD đứng lại ở nhánh sạch."""
    _git(repo, "checkout", "-qb", "khac")
    (repo / "k.py").write_text(f"u = '{GIA}'\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lo")
    _git(repo, "checkout", "-q", "-")


@pytest.mark.parametrize("lenh", ["git push origin khac", "git push --all", "git push --tags origin", "git push origin khac:khac", "git push --mirror"])
def test_push_dang_day_nhanh_ngoai_head_thi_quet_ca_nhanh_khac(repo, lenh):
    _bi_mat_tren_nhanh_khac(repo)
    r = _hook("Bash", {"command": lenh}, cwd=repo)
    assert r.returncode == 2 and "k.py" in r.stderr, (lenh, r.stderr)
    assert "Xk9mQ2pLw" not in r.stderr


@pytest.mark.parametrize("lenh", ["git push", "git push origin", "git push origin HEAD", "git push -u origin HEAD"])
def test_push_dang_thuong_chi_quet_head_khong_bao_oan_nhanh_khac(repo, lenh):
    """Đẩy trơn chỉ đẩy nhánh hiện tại: bí mật ở nhánh khác (chưa đẩy) không được chặn oan."""
    _bi_mat_tren_nhanh_khac(repo)
    r = _hook("Bash", {"command": lenh}, cwd=repo)
    assert r.returncode == 0, (lenh, r.stderr)


def test_push_nhanh_hien_tai_dat_ten_ro_van_la_dang_thuong(repo):
    _bi_mat_tren_nhanh_khac(repo)
    hien_tai = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert _hook("Bash", {"command": f"git push origin {hien_tai}"}, cwd=repo).returncode == 0


# --- lệnh đăng ký trong settings.json, chạy THẬT bằng bash như Claude Code (Windows dùng Git Bash)

_BASH = shutil.which("bash")


def _lenh_dang_ky() -> str:
    cau_hinh = json.loads((GOC / ".claude" / "settings.json").read_text(encoding="utf-8"))
    lenh = {h["command"] for m in cau_hinh["hooks"]["PreToolUse"] for h in m["hooks"]}
    assert len(lenh) == 1, "hai matcher phải dùng cùng một lệnh đăng ký"
    return lenh.pop()


def _chay_dang_ky(thu_muc_du_an: Path, vao: dict, path: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(thu_muc_du_an)}
    if path is not None:
        env["PATH"] = path
    return subprocess.run([_BASH, "-c", _lenh_dang_ky()], input=json.dumps(vao), capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)


_GHI_DU_LIEU = {"tool_name": "Write", "tool_input": {"file_path": "src/data/x.txt"}, "cwd": str(GOC)}
_GHI_BINH_THUONG = {"tool_name": "Write", "tool_input": {"file_path": "src/core/x.py"}, "cwd": str(GOC)}


@pytest.mark.skipif(_BASH is None, reason="cần bash (Git Bash trên Windows)")
class TestLenhDangKy:
    def test_hook_chay_that_chan_va_cho_qua(self):
        assert _chay_dang_ky(GOC, _GHI_DU_LIEU).returncode == 2
        assert _chay_dang_ky(GOC, _GHI_BINH_THUONG).returncode == 0

    def test_thieu_han_tep_hook_thi_cho_qua_co_chu_y(self, tmp_path):
        """Nhánh cũ chưa có hook không bị khoá mọi lệnh. Tệp bị xoá thì hiện trong diff và test này."""
        assert _chay_dang_ky(tmp_path, _GHI_DU_LIEU).returncode == 0

    @pytest.mark.parametrize("noi_dung", ["raise SystemExit(1)\n", "import khong_co_goi_nay_dau\n", "raise SystemExit(7)\n"])
    def test_hook_chet_hoac_thoat_ma_la_thi_chan_khong_im_lang(self, tmp_path, noi_dung):
        (tmp_path / ".claude" / "hooks").mkdir(parents=True)
        (tmp_path / ".claude" / "hooks" / "cong_cung.py").write_text(noi_dung, encoding="utf-8")
        r = _chay_dang_ky(tmp_path, _GHI_BINH_THUONG)
        assert r.returncode == 2, r.stderr

    def test_khong_co_python_thi_chan_khong_im_lang(self, tmp_path):
        r = _chay_dang_ky(GOC, _GHI_BINH_THUONG, path=str(tmp_path))
        assert r.returncode == 2 and "không có Python" in r.stderr, r.stderr
