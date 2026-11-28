"""Phần chạy được không cần GPU của `offline_training/demo_colab.py`: cấu hình server, biến của Brain, chép/vá trọng số, các phép chấm và báo cáo không chứa token."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from email.parser import BytesParser
from email.policy import default as chinh_sach
from pathlib import Path

import pytest

from offline_training import demo_colab as dc
from offline_training.kiem_tich_hop_body import DAT, TRUOT, Brain
from sample_data.make_sample_data import HOA_DON_CUOC, LECH_HOA_DON, QUY_CHE
from src.core.engine import chon_backend
from src.core.serving import kiem_url_noi_bo

TOKEN = "t" * 64


def test_hai_server_khong_vuot_gpu_va_dung_co_p2() -> None:
    may = dc.cac_may_chu({})
    assert sum(float(m.phan_gpu) for m in may) <= 0.92
    for m in may:
        lenh = dc.lenh_vllm(m, Path("/content/models") / m.nguon)
        assert "--disable-log-requests" in lenh and "--host=127.0.0.1" in lenh
    vision = dc.lenh_vllm(may[1], Path("x"))
    assert json.loads(vision[vision.index("--limit-mm-per-prompt") + 1]) == {"image": 2}


def test_bien_moi_truong_doi_cau_hinh_khong_sua_ma() -> None:
    may = dc.cac_may_chu({"TEXT_GPU_FRACTION": "0.5", "DEMO_TEXT_MODEL": "anser-v3-awq"})
    assert may[0].phan_gpu == "0.5" and may[0].nguon == "anser-v3-awq"


def test_env_brain_goi_server_noi_bo_va_khong_mang_database() -> None:
    nen = {"DATABASE_URL": "postgresql://x", "VLLM_N8N_BASE_URL": "http://127.0.0.1:9", "BODY_CALLBACK_URL": "http://x", "PATH": "/bin"}
    env = dc.env_brain(nen, TOKEN, Path("/content/ANSER_AI"), dc.cac_may_chu({}))
    for khoa in ("DATABASE_URL", "VLLM_N8N_BASE_URL", "BODY_CALLBACK_URL"):
        assert khoa not in env
    assert env["PATH"] == "/bin" and env["API_AUTH_TOKEN"] == TOKEN
    for khoa in ("VLLM_BASE_URL", "VLLM_VISION_BASE_URL"):
        kiem_url_noi_bo(env[khoa], khoa)      # R2: ném nếu không phải máy nội bộ
    assert chon_backend(env["ENV"], env["VLLM_BASE_URL"], env["VLLM_VISION_BASE_URL"]) == ("server", "server")


def test_chep_trong_so_bo_qua_tep_da_co_va_thu_muc_con(tmp_path: Path) -> None:
    nguon = tmp_path / "drive"
    (nguon / "_cu").mkdir(parents=True)
    (nguon / "config.json").write_text("{}", encoding="utf-8")
    (nguon / "w.safetensors").write_bytes(b"123")
    (nguon / "_cu" / "x").write_text("x", encoding="utf-8")
    dich = tmp_path / "models"
    assert dc.chep_thu_muc(nguon, dich) == 2
    assert dc.chep_thu_muc(nguon, dich) == 0
    assert not (dich / "_cu").exists()


def test_manifest_bat_tep_sai_va_tep_thieu(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"dung")
    (tmp_path / "b").write_bytes(b"sai roi")
    dong = [f"{hashlib.sha256(b'dung').hexdigest()}  a", f"{hashlib.sha256(b'goc').hexdigest()}  b", f"{'0' * 64} *c"]
    (tmp_path / "MANIFEST.sha256").write_text("\n".join(dong) + "\n", encoding="utf-8")
    assert dc.kiem_manifest(tmp_path) == ["sai mã băm b", "thiếu c"]
    (tmp_path / "MANIFEST.sha256").unlink()
    assert dc.kiem_manifest(tmp_path) == []


def test_va_tokenizer_chep_ban_goc_va_cat_jinja(tmp_path: Path) -> None:
    goc, model = tmp_path / "goc", tmp_path / "model"
    goc.mkdir()
    model.mkdir()
    (goc / "tokenizer.json").write_text("moi", encoding="utf-8")
    (model / "tokenizer.json").write_text("cu", encoding="utf-8")
    (model / "chat_template.jinja").write_text("j", encoding="utf-8")
    dc.va_tokenizer(model, goc)
    assert (model / "tokenizer.json").read_text(encoding="utf-8") == "moi"
    assert not (model / "chat_template.jinja").exists() and (model / "chat_template.jinja.bak").exists()


def _task(tra_loi: str, status: str = "completed") -> dict:
    return {"status": status, "result": {"answer": tra_loi}}


@pytest.mark.parametrize("task, trang_thai", [
    (_task("Thuế GTGT 8% là 160.000 đồng."), DAT),
    (_task("Thuế là 200.000 đồng."), TRUOT),
    (_task("160.000 mock_response"), TRUOT),
    (_task("160.000", status="failed"), TRUOT),
    ("chuỗi lỗi", TRUOT),
])
def test_cham_cau_tra_loi(task: object, trang_thai: str) -> None:
    assert dc.cham_tra_loi(task, dc.DAP_AN_VAT)[0] == trang_thai


def _ocr(tong: object, duyet: bool) -> dict:
    return {"success": True, "invoice": {"total": tong}, "needs_manual_review": duyet, "validation": {"issues": []}}


def test_cham_hoa_don_doi_so_in_va_co_xem_lai() -> None:
    tong = int(HOA_DON_CUOC["total"])
    assert dc.cham_doc_hoa_don(200, _ocr(float(tong), False), tong, False)[0] == DAT
    assert dc.cham_doc_hoa_don(200, _ocr(tong + LECH_HOA_DON, True), tong + LECH_HOA_DON, True)[0] == DAT
    # Model "sửa hộ" số in sai thành số đúng, hoặc không đòi người xem tờ lệch: đều trượt.
    assert dc.cham_doc_hoa_don(200, _ocr(tong, True), tong + LECH_HOA_DON, True)[0] == TRUOT
    assert dc.cham_doc_hoa_don(200, _ocr(tong + LECH_HOA_DON, False), tong + LECH_HOA_DON, True)[0] == TRUOT
    assert dc.cham_doc_hoa_don(200, _ocr(None, False), tong, False)[0] == TRUOT
    assert dc.cham_doc_hoa_don(503, "Vision runtime unavailable", tong, False)[0] == TRUOT


def test_cham_tim_tai_lieu() -> None:
    assert dc.cham_tim_tai_lieu(200, {"passages": [{"text": "tối đa 45 ngày", "source": "q"}]}, "45 ngày")[0] == DAT
    assert dc.cham_tim_tai_lieu(200, {"passages": [{"text": "30 ngày", "source": "q"}]}, "45 ngày")[0] == TRUOT
    assert dc.cham_tim_tai_lieu(200, {"passages": []}, "45 ngày")[0] == TRUOT


def test_bao_cao_len_drive_khong_chua_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ra = tmp_path / "ra"
    ra.mkdir()
    (ra / "brain.log").write_text("khởi động", encoding="utf-8")
    monkeypatch.setattr(dc, "RA", ra)
    monkeypatch.setattr(dc, "DRIVE", tmp_path / "drive")
    monkeypatch.setenv("API_AUTH_TOKEN", TOKEN)
    thu_muc = dc.ghi_bao_cao({"commit": "abc", "may_ham": "x.trycloudflare.com", "hang": []})
    assert thu_muc is not None
    assert all(TOKEN not in f.read_text(encoding="utf-8") for f in thu_muc.iterdir())
    khoi = dc.khoi_ket_noi("https://x.trycloudflare.com", TOKEN)
    assert f"BRAIN_API_TOKEN={TOKEN}" in khoi and "BRAIN_URL=https://x.trycloudflare.com" in khoi


def test_cloudflared_ghim_ban_va_ma_bam() -> None:
    assert "/releases/download/" in dc.CLOUDFLARED_URL and "latest" not in dc.CLOUDFLARED_URL
    assert len(dc.CLOUDFLARED_SHA256) == 64


def test_multipart_mang_truong_form_cua_kho_tri_thuc(monkeypatch: pytest.MonkeyPatch) -> None:
    bat_duoc: dict = {}

    class _PhanHoi:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self) -> bytes:
            return b"{}"

    def gia(req: urllib.request.Request, timeout: float = 0):
        bat_duoc["kieu"] = req.get_header("Content-type")
        bat_duoc["than"] = req.data
        return _PhanHoi()

    monkeypatch.setattr(urllib.request, "urlopen", gia)
    Brain("http://127.0.0.1:1", TOKEN).goi("POST", "/knowledge/documents", multipart=("quy_che.txt", QUY_CHE.encode()), truong={"workspace_id": "default"})
    msg = BytesParser(policy=chinh_sach).parsebytes(b"Content-Type: " + bat_duoc["kieu"].encode() + b"\r\n\r\n" + bat_duoc["than"])
    phan = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
    assert phan["workspace_id"].get_payload().strip() == "default"
    assert phan["file"].get_filename() == "quy_che.txt"
    assert phan["file"].get_payload(decode=True) == QUY_CHE.encode()
