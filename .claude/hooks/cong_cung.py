"""
.claude/hooks/cong_cung.py — cổng cứng cho Claude Code (hook PreToolUse): chạy dù model quyết gì.

Chặn (mã thoát 2, Claude Code huỷ lời gọi và đưa lý do cho model):
  1. Write/Edit/NotebookEdit vào `src/data/` (R2: nơi có thể chứa dữ liệu khách) hay vào tệp `.env` (R2b: đổi bí mật phải hỏi chủ dự án).
  2. `git commit`: tệp đang đổi có chuỗi giống bí mật (R2b), hoặc `ruff check` đỏ trên tệp .py đang đổi.
  3. `git push`: commit chưa có trên remote nào thêm dòng chứa chuỗi giống bí mật.

Mẫu bí mật KHÔNG viết lại ở đây (R4): dùng `quet` và `scan_secrets` của `offline_training/quet_secret_pre_commit.py`. Không bao giờ in giá trị tìm thấy,
chỉ tên tệp và số chỗ khớp (đầu ra hook đi vào nhật ký trò chuyện).

Cổng bí mật hỏng (không import được, git lỗi) thì CHẶN: cổng an toàn không được im lặng cho qua. Thiếu `ruff` thì chỉ cảnh báo.
Đây là lớp sớm hơn pre-commit và CI, không thay chúng: chỉ áp cho Claude Code, không áp cho người gõ lệnh hay công cụ khác.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
TOI_DA_BYTE = 2_000_000

# `git commit` / `git push`, kể cả `git -C <dir> commit` và nằm sau `&&`, `;`, `|`.
_LENH_GIT = re.compile(r"(?:^|[;&|\n(]\s*)git(?:\s+(?:-C|-c)\s+(?:\"[^\"]*\"|'[^']*'|\S+))*\s+(commit|push)\b")
_CD = re.compile(r"(?:^|[;&|\n]\s*)(?:cd|Set-Location)\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)")
_GIT_C = re.compile(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")


class Chan(Exception):
    """Lời gọi bị chặn, kèm lý do cho model."""


def _duong_tuong_doi(duong: str, cwd: Path) -> str | None:
    """Đường dẫn tương đối so với gốc repo (kiểu posix, chữ thường), None nếu nằm ngoài repo."""
    p = Path(duong)
    if not p.is_absolute():
        p = cwd / p
    try:
        return Path(os.path.normpath(p)).relative_to(GOC).as_posix().lower()
    except ValueError:
        return None


def kiem_ghi_tep(duong: str, cwd: Path) -> None:
    rel = _duong_tuong_doi(duong, cwd)
    if rel is None:
        return
    if rel == "src/data" or rel.startswith("src/data/"):
        raise Chan("R2: không ghi vào src/data/ (nơi có thể chứa dữ liệu khách). Cần thật thì nhờ chủ dự án sửa tay.")
    ten = rel.rsplit("/", 1)[-1]
    if ten == ".env" or (ten.startswith(".env.") and ten != ".env.example"):
        raise Chan("R2b: không ghi tệp .env. Đổi cách giữ bí mật phải hỏi chủ dự án trước.")


def _thu_muc_repo(lenh: str, cwd: Path) -> Path:
    """Repo mà lệnh git sẽ chạy trong đó: `git -C`, rồi `cd` cuối cùng trước lệnh git, rồi cwd."""
    m_git = _LENH_GIT.search(lenh)
    truoc = lenh[: m_git.end()] if m_git else lenh
    dich = [m.group(1) for m in _GIT_C.finditer(truoc)] or [m.group(1) for m in _CD.finditer(truoc)]
    if not dich:
        return cwd
    d = dich[-1].strip("\"'")
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", d):      # đường kiểu Git Bash: /d/AI_ANSER
        d = f"{d[1]}:{d[2:]}"
    p = Path(os.path.expandvars(os.path.expanduser(d)))
    p = p if p.is_absolute() else cwd / p
    return p if p.is_dir() else cwd


def _git(repo: Path, *tham_so: str) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *tham_so], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=90)
    if r.returncode != 0:
        raise RuntimeError(f"git {tham_so[0]} trả mã {r.returncode}")
    return r.stdout


def _bo_quet():
    if str(GOC) not in sys.path:
        sys.path.insert(0, str(GOC))
    from offline_training import quet_secret_pre_commit as q

    return q


def tep_dang_doi(repo: Path) -> list[str]:
    """Mọi tệp sửa, thêm hay chưa theo dõi (rộng hơn "đã staged": `git add -A && git commit` chưa staged gì lúc hook chạy)."""
    ra: list[str] = []
    muc = _git(repo, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    i = 0
    while i < len(muc):
        m = muc[i]
        i += 1
        if len(m) < 4:
            continue
        trang_thai, ten = m[:2], m[3:]
        if "R" in trang_thai or "C" in trang_thai:
            i += 1                                           # đường dẫn cũ đứng ngay sau
        if "D" in trang_thai:
            continue
        ra.append(ten)
    return ra


def kiem_commit(repo: Path) -> None:
    goc_git = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    tep = [t for t in tep_dang_doi(goc_git) if (goc_git / t).is_file() and (goc_git / t).stat().st_size <= TOI_DA_BYTE]
    if (goc_git / _git(goc_git, "rev-parse", "--git-path", "MERGE_HEAD").strip()).is_file():
        # Đang gộp: tệp nguyên văn từ nhánh được kéo vào đã nằm trên remote (kiem_push cũng không quét commit đã có trên remote), nên chỉ quét tệp
        # KHÁC cả hai phía (xung đột đã giải tay) và tệp chưa theo dõi. Quét hết thì mọi lần kéo nhánh tính năng vào đều báo oan fixture của người khác.
        khac = set(_git(goc_git, "diff", "--name-only", "MERGE_HEAD").splitlines())
        chua_theo_doi = set(_git(goc_git, "ls-files", "--others", "--exclude-standard").splitlines())
        tep = [t for t in tep if t in khac or t in chua_theo_doi]
    if not tep:
        return
    q = _bo_quet()
    dinh = []
    cu = os.getcwd()
    os.chdir(goc_git)                                        # `quet` so danh sách bỏ qua theo đường tương đối
    try:
        dinh = q.quet(tep)
    finally:
        os.chdir(cu)
    if dinh:
        ds = "; ".join(f"{ten} ({len(h)} chỗ)" for ten, h in dinh)
        raise Chan(f"R2b: thấy chuỗi giống bí mật trong tệp sắp commit: {ds}. Giá trị thật thì XOAY nó trước rồi mới dọn; "
                   "fixture của test thì thêm vào BO_QUA của offline_training/quet_secret_pre_commit.py. Không in giá trị ra.")
    py = [t for t in tep if t.endswith(".py")]
    if py and goc_git == GOC:
        r = subprocess.run([sys.executable, "-m", "ruff", "check", *py], cwd=goc_git, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
        if r.returncode == 1 and "No module named" not in r.stderr:
            raise Chan("ruff check đỏ trên tệp đang đổi, sửa trước khi commit:\n" + r.stdout[-1500:])
        if r.returncode != 0:
            print("cổng cứng: không chạy được ruff, bỏ qua bước này (CI vẫn kiểm).", file=sys.stderr)


def kiem_push(repo: Path) -> None:
    goc_git = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    log = _git(goc_git, "log", "HEAD", "--not", "--remotes", "-p", "--no-color", "--format=@@COMMIT %h")
    if not log.strip():
        return
    q = _bo_quet()
    commit, tep, dinh = "?", "", {}
    for dong in log.splitlines():
        if dong.startswith("@@COMMIT "):
            commit = dong[9:].strip()
        elif dong.startswith("+++ "):
            tep = dong[6:] if dong.startswith("+++ b/") else ""
        elif dong.startswith("+") and tep not in q.BO_QUA and Path(tep).suffix.lower() not in q.DUOI_BO_QUA and q.scan_secrets(dong):
            dinh[(commit, tep)] = dinh.get((commit, tep), 0) + 1
    if dinh:
        ds = "; ".join(f"{c} {t} ({n} dòng)" for (c, t), n in dinh.items())
        raise Chan(f"R2b: commit sắp đẩy thêm dòng giống bí mật: {ds}. KHÔNG đẩy. Giá trị thật thì xoay trước, báo chủ dự án.")


def kiem(du_lieu: dict) -> None:
    cong_cu = du_lieu.get("tool_name", "")
    vao = du_lieu.get("tool_input") or {}
    cwd = Path(du_lieu.get("cwd") or GOC)
    if cong_cu in ("Write", "Edit", "NotebookEdit"):
        duong = vao.get("file_path") or vao.get("notebook_path")
        if duong:
            kiem_ghi_tep(str(duong), cwd)
        return
    if cong_cu not in ("Bash", "PowerShell"):
        return
    lenh = str(vao.get("command") or "")
    viec = {m.group(1) for m in _LENH_GIT.finditer(lenh)}
    if not viec:
        return
    try:
        repo = _thu_muc_repo(lenh, cwd)
        if "commit" in viec:
            kiem_commit(repo)
        if "push" in viec:
            kiem_push(repo)
    except Chan:
        raise
    except Exception as e:  # cổng an toàn hỏng thì chặn, nói rõ loại lỗi (không in nội dung)
        raise Chan(f"cổng cứng không chạy được ({type(e).__name__}); chặn để không bỏ sót bí mật. Chạy tay: "
                   "python offline_training/quet_secret_pre_commit.py <tệp>, hoặc báo chủ dự án.") from e


def main() -> int:
    for luong in (sys.stdin, sys.stderr, sys.stdout):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        du_lieu = json.load(sys.stdin)
    except ValueError:
        print("cổng cứng: không đọc được đầu vào hook.", file=sys.stderr)
        return 0
    try:
        kiem(du_lieu)
    except Chan as e:
        print(f"CHẶN (cổng cứng): {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
