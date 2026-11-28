"""
offline_training/kiem_tich_hop_body.py — nhìn Brain bằng mắt của BODY: gọi đúng những đường, đúng các header mà `frontend/src/server/brain.ts` gọi.

    python offline_training/kiem_tich_hop_body.py --tu-bat                 # bật Brain LOCAL (không GPU) rồi kiểm; chạy được ở máy dev
    BRAIN_URL=https://… BRAIN_API_TOKEN=… BRAIN_KB_WORKSPACE=… \\
        python offline_training/kiem_tich_hop_body.py                      # kiểm một Brain đang chạy (Colab, VPS), dùng ĐÚNG tên biến của Body
    python offline_training/kiem_tich_hop_body.py --can-model --json kq.json   # buổi demo thật: chat phải do model sinh, không được là mock
    python offline_training/kiem_tich_hop_body.py --tu-bat --voi-brain-ts      # thêm: chạy CHÍNH brain.ts của Body (Node >= 22.18) để chứng minh Body đọc được Brain

VÌ SAO CÓ FILE NÀY
------------------
`kiem_server_that.py` kiểm Brain tự đứng được. `chay_that_dau_cuoi.py` kiểm Brain trên GPU. Không cái nào kiểm CHỖ NỐI: Body gọi Brain bằng header gì, theo thứ tự nào (`/chat` rồi hỏi
`/api/v1/task/{id}`), gửi file bằng multipart ra sao, và đọc những trường nào của `/health` để hiện "AI đang bật/tắt". Chỗ nối là nơi demo hỏng: token lệch một ký tự, kho tri thức khác
tên giữa hai bên, Brain nguội 1 đến 3 phút ở lượt chat đầu — mỗi lỗi nhìn từ giao diện Body đều chỉ là "AI không trả lời".

File này là bản Python của những lời gọi đó, chạy TRƯỚC khi mở Body cho khách xem. Nó không thay `doi_chieu_hop_dong_body.py` (so SCHEMA đầu vào với `brain.ts`): cái đó bắt lệch trường, cái này bắt lệch hành vi lúc chạy.

Mỗi bước có đáp án tính tay (R1): VAT 2.200.000, báo giá 1.139.000, doanh thu và lãi gộp của báo cáo mẫu, tám phát hiện trên bảy mã của `sample_data/ton_kho_mau.xlsx`. Dữ liệu hoàn toàn hư cấu (R2).

BA TRẠNG THÁI NGOÀI ĐẠT/TRƯỢT
-----------------------------
    mock      chat trả câu của chế độ LOCAL (không có model). Không phải đạt: với `--can-model` là TRƯỢT.
    canh_bao  điều đáng biết nhưng không chặn demo (kho tri thức chưa nạp, Brain không kiểm token ở chế độ LOCAL, chat chậm hơn 60 giây mặc định của Body).
    bo_qua    bước bị tắt bằng cờ (`--bo-chat`).
Mã thoát: 0 mọi bước bắt buộc đạt; 1 có bước bắt buộc trượt; 2 không nối được Brain (không có gì để kết luận).
Bảng và JSON KHÔNG chứa token; URL chỉ in tên máy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from offline_training.kiem_server_that import (  # noqa: E402  (một định nghĩa cho hai phép kiểm: R4)
    QUOTE_VAO,
    VAT_VAO,
    cong_trong,
)
from sample_data.make_sample_data import DONG, LOI_GIEO, ghi_xlsx  # noqa: E402

DAT, TRUOT, MOCK, CANH_BAO, BO_QUA = "dat", "truot", "mock", "canh_bao", "bo_qua"

# Danh tính y như Body gửi: UUID của người dùng và của kho. Cố định để lượt chạy nào cũng lặp lại được.
USER_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "kiem-tich-hop-body.nguoi-dung"))
STORE_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "kiem-tich-hop-body.kho"))
KHOA_TAM = "kiem-tich-hop-" + "t" * 32      # token DÙNG MỘT LẦN cho tiến trình `--tu-bat`; không phải bí mật của ai
HAN_MAC_DINH_BODY_S = 60                    # `TIMEOUT_MS.chat` mặc định của brain.ts khi không đặt BRAIN_CHAT_TIMEOUT_MS

# Một định nghĩa (R4): mã có lỗi và số dòng lấy từ chính bộ sinh dữ liệu mẫu, không chép tay. Tệp .xlsx không được commit (gitignore),
# nên công cụ TỰ SINH vào thư mục tạm thay vì đòi người chạy sinh trước.
MA_TON_KHO_CO_LOI = set(LOI_GIEO)           # bảy mã gieo lỗi có chủ đích; thêm hay bớt một mã ở bộ sinh thì phép kiểm đổi theo
SO_DONG_TON_KHO = len(DONG)

# Báo cáo mẫu, hư cấu, tính tay được:
#   09/2026: doanh thu 10.000.000, giá vốn 7.000.000 → lãi gộp 3.000.000.
#   10/2026: doanh thu 17.000.000 trong đó 5.000.000 CHƯA CÓ giá vốn → giá vốn 8.400.000 chỉ trên 12.000.000 → lãi gộp 3.600.000 (không phải 17.000.000 − 8.400.000);
#            trừ chi phí 2.000.000 → lãi ròng 1.600.000.  Phủ giá vốn chung = 22/27 = 81,5%.
BAO_CAO_VAO: dict[str, Any] = {
    "granularity": "month", "periods_back": 3,
    "sales": [
        {"date": "2026-09-10", "revenue": 10_000_000, "product": "Dầu AW46", "quantity": 10, "cogs": 7_000_000},
        {"date": "2026-10-12", "revenue": 12_000_000, "product": "Dầu AW46", "quantity": 12, "cogs": 8_400_000},
        {"date": "2026-10-20", "revenue": 5_000_000, "product": "Mỡ chịu nhiệt", "quantity": 5, "cogs": None},
    ],
    "expenses": [{"date": "2026-10-05", "amount": 2_000_000, "category": "Lương"}],
}
# Hai cách "thiếu" KHÁC NHAU, và Brain cố ý trả khác nhau (AGENTS R1):
#   có doanh thu mà không dòng nào có giá vốn → phủ = 0,0% (ĐÃ ĐO, và bằng không), độ tin cậy "thấp", kèm cảnh báo;
#   chỉ có chi phí, không có doanh thu       → phủ = null (CHƯA ĐO), độ tin cậy "không có dữ liệu".
BAO_CAO_KHONG_GIA_VON: dict[str, Any] = {
    "granularity": "month", "periods_back": 1,
    "sales": [{"date": "2026-10-12", "revenue": 12_000_000, "product": "Dầu AW46", "quantity": 12, "cogs": None}],
}
BAO_CAO_CHI_CO_CHI_PHI: dict[str, Any] = {
    "granularity": "month", "periods_back": 1, "sales": [],
    "expenses": [{"date": "2026-10-05", "amount": 2_000_000, "category": "Lương"}],
}
CAU_CHAT = "Xin chào, bạn giúp được gì cho kho của tôi?"


# ----------------------------------------------------------------------------------------------------------------------------
# Phần THUẦN: nhận phản hồi đã giải mã, trả (trạng thái, chi tiết). Tách ra để test được mà không bật server, và để test có thể
# làm chúng ĐỎ bằng một phản hồi sai (một phép chấm chỉ biết xanh thì không đáng tin).
# ----------------------------------------------------------------------------------------------------------------------------
Chi = tuple[str, str]


def kiem_suc_khoe(h: Any) -> Chi:
    if not isinstance(h, dict):
        return TRUOT, "/health không trả JSON"
    if h.get("status") != "ok":
        return TRUOT, f"status={h.get('status')!r}"
    if h.get("degraded"):
        return TRUOT, "Brain đang degraded (mạch ngắt model, hàng đợi hoặc VRAM) — sửa trước khi demo"
    return DAT, f"status=ok degraded=False engine_ready={h.get('engine_ready')} vision_ready={h.get('vision_ready')}"


def kiem_truong_body_doc(h: Any) -> Chi:
    """`/api/ai/health` của Body đọc đúng ba trường này; thiếu `auth_enabled` thì Body tưởng là Brain cũ và bỏ cảnh báo."""
    if not isinstance(h, dict):
        return TRUOT, "/health không trả JSON"
    thieu = [k for k in ("engine_ready", "vision_ready", "auth_enabled") if k not in h]
    return (TRUOT, f"thiếu trường Body đọc: {', '.join(thieu)}") if thieu else (DAT, "đủ engine_ready, vision_ready, auth_enabled")


def kiem_xac_thuc(co_token: bool, auth_enabled: Any, ma_khong_token: int, ma_sai_token: int, ma_dung_token: int) -> Chi:
    bi_chan = (401, 403)
    if not co_token:
        if auth_enabled:
            return TRUOT, "Brain đòi token nhưng chưa đặt BRAIN_API_TOKEN ở đây — không gọi được gì"
        return CANH_BAO, "Brain KHÔNG kiểm token (chấp nhận được ở LOCAL; KHÔNG mở ra ngoài khi chưa đặt API_AUTH_TOKEN)"
    if auth_enabled is not True:
        return TRUOT, f"đã đưa token nhưng /health báo auth_enabled={auth_enabled!r}: Brain chưa đặt API_AUTH_TOKEN, mở toang"
    loi = []
    if ma_khong_token not in bi_chan:
        loi.append(f"không token mà vào được (http={ma_khong_token})")
    if ma_sai_token not in bi_chan:
        loi.append(f"token sai mà vào được (http={ma_sai_token})")
    if ma_dung_token != 200:
        loi.append(f"token đúng mà bị từ chối (http={ma_dung_token}) — BRAIN_API_TOKEN lệch API_AUTH_TOKEN?")
    return (TRUOT, "; ".join(loi)) if loi else (DAT, f"không token → {ma_khong_token}, sai token → {ma_sai_token}, đúng token → 200")


def kiem_vat(r: Any) -> Chi:
    ok = isinstance(r, dict) and r.get("calculated_total") == 2_200_000 and r.get("is_valid") is True
    return (DAT if ok else TRUOT), f"calculated_total={r.get('calculated_total') if isinstance(r, dict) else r!r} (đáp án tính tay: 2.200.000)"


def kiem_bao_gia(r: Any) -> Chi:
    gia = r.get("quote", {}).get("quoted_price") if isinstance(r, dict) and isinstance(r.get("quote"), dict) else None
    return (DAT if gia == 1_139_000 else TRUOT), f"quoted_price={gia} (đáp án tính tay: 1.139.000)"


def kiem_bao_cao(r: Any) -> Chi:
    if not isinstance(r, dict):
        return TRUOT, "không trả JSON"
    ky = {p.get("period"): p for p in r.get("periods", []) if isinstance(p, dict)}
    p9, p10 = ky.get("2026-09") or {}, ky.get("2026-10") or {}
    mong = [("09/2026 doanh thu", p9.get("revenue"), 10_000_000), ("09/2026 lãi gộp", p9.get("gross_profit"), 3_000_000),
            ("10/2026 doanh thu", p10.get("revenue"), 17_000_000), ("10/2026 lãi gộp", p10.get("gross_profit"), 3_600_000),
            ("10/2026 lãi ròng", p10.get("net_profit"), 1_600_000)]
    sai = [f"{ten}={co} (phải {can})" for ten, co, can in mong if co != can]
    ex: dict[str, Any] = r["explain"] if isinstance(r.get("explain"), dict) else {}
    # Bốn trường này Body khai là BẮT BUỘC và hiển thị: thiếu thì `?? 0` bên Body hiện 0%, một con số trông như kết quả đo.
    thieu = [k for k in ("cogs_coverage_pct", "confidence", "formula", "period_count") if k not in ex]
    if thieu:
        sai.append(f"explain thiếu {', '.join(thieu)}")
    elif ex.get("cogs_coverage_pct") != 81.5:
        sai.append(f"cogs_coverage_pct={ex.get('cogs_coverage_pct')} (phải 81,5)")
    hang_thieu_gv = [p for p in r.get("products", []) if isinstance(p, dict) and p.get("product") == "Mỡ chịu nhiệt"]
    if not hang_thieu_gv or hang_thieu_gv[0].get("missing_cogs") is not True or hang_thieu_gv[0].get("gross_profit") is not None:
        sai.append("mặt hàng chưa có giá vốn không được ghi missing_cogs=true và gross_profit=null (không được điền 0)")
    return (TRUOT, "; ".join(sai)) if sai else (DAT, "doanh thu, giá vốn, lãi gộp, lãi ròng, phủ 81,5% đều khớp tính tay; hàng thiếu giá vốn ghi null")


def kiem_bao_cao_thieu_gia_von(co_doanh_thu: Any, chi_co_chi_phi: Any) -> Chi:
    """Hai nhánh thiếu dữ liệu của `build_report`; cả hai PHẢI trả đủ bốn khoá Body hiển thị, giá trị tự nói mình là gì."""
    def khoa_thieu(r: Any) -> list[str]:
        ex = r.get("explain") if isinstance(r, dict) else None
        return [k for k in ("cogs_coverage_pct", "confidence", "formula", "period_count") if not isinstance(ex, dict) or k not in ex]

    loi = []
    if khoa_thieu(co_doanh_thu) or khoa_thieu(chi_co_chi_phi):
        return TRUOT, f"nhánh thiếu dữ liệu bỏ mất khoá của explain ({khoa_thieu(co_doanh_thu) or khoa_thieu(chi_co_chi_phi)}): Body sẽ hiện 0% thay vì nhãn trung thực"
    a, b = co_doanh_thu["explain"], chi_co_chi_phi["explain"]
    if a.get("cogs_coverage_pct") != 0.0 or a.get("confidence") == "cao" or not co_doanh_thu.get("warnings"):
        loi.append(f"có doanh thu mà không giá vốn: phủ={a.get('cogs_coverage_pct')!r}, tin cậy={a.get('confidence')!r}, "
                   f"cảnh báo={'có' if co_doanh_thu.get('warnings') else 'KHÔNG'} (phải 0,0 / không phải 'cao' / có cảnh báo)")
    if b.get("cogs_coverage_pct") is not None or b.get("confidence") != "không có dữ liệu":
        loi.append(f"chỉ có chi phí: phủ={b.get('cogs_coverage_pct')!r}, tin cậy={b.get('confidence')!r} (phải null / 'không có dữ liệu': chưa đo, không phải 0%)")
    return (TRUOT, "; ".join(loi)) if loi else (DAT, "có doanh thu thiếu giá vốn → 0,0% + 'thấp' + cảnh báo; chỉ có chi phí → null + 'không có dữ liệu'")


def kiem_ton_kho(r: Any) -> Chi:
    if not isinstance(r, dict) or not isinstance(r.get("import"), dict):
        return TRUOT, "không trả khối import"
    dong = r["import"].get("rows_parsed")
    audit = r.get("audit")
    if not isinstance(audit, dict):
        return TRUOT, f"audit=null, lý do: {r.get('audit_skipped_reason')!r}"
    ma = {str(f.get("code")) for f in audit.get("findings", []) if isinstance(f, dict)}
    sai: list[str] = []
    if dong != SO_DONG_TON_KHO:
        sai.append(f"đọc {dong} dòng (phải {SO_DONG_TON_KHO})")
    if ma != MA_TON_KHO_CO_LOI:
        sai.append(f"thiếu mã {sorted(MA_TON_KHO_CO_LOI - ma)}" if MA_TON_KHO_CO_LOI - ma else "")
        sai.append(f"gắn cờ oan {sorted(ma - MA_TON_KHO_CO_LOI)}" if ma - MA_TON_KHO_CO_LOI else "")
    sai = [s for s in sai if s]
    return (TRUOT, "; ".join(sai)) if sai else (DAT, f"{SO_DONG_TON_KHO} dòng, {len(audit.get('findings', []))} phát hiện trên đúng {len(MA_TON_KHO_CO_LOI)} mã gieo sẵn, không gắn cờ mã nào khác")


def kiem_kho_tri_thuc(ma: int, r: Any, kb_ready: Any) -> Chi:
    if ma == 200 and isinstance(r, dict) and isinstance(r.get("documents"), list):
        return (DAT if kb_ready else CANH_BAO), (f"liệt kê được {len(r['documents'])} tài liệu" if kb_ready else
                                                  "liệt kê được nhưng kb_ready=false: hỏi luật/tài liệu nội bộ sẽ chưa trả được (cần chromadb, sentence-transformers)")
    return CANH_BAO, f"http={ma}: kho tri thức chưa dùng được; demo phần tài liệu nội bộ sẽ không chạy"


def kiem_chat(task: Any, giay: float, can_model: bool) -> Chi:
    if not isinstance(task, dict):
        return TRUOT, "không lấy được kết quả task"
    if task.get("status") == "failed":
        return TRUOT, f"task failed: {str(task.get('error'))[:120]}"
    if task.get("status") != "completed":
        return TRUOT, f"task chưa xong sau {giay:.0f}s (status={task.get('status')!r})"
    res: dict[str, Any] = task["result"] if isinstance(task.get("result"), dict) else {}
    tra_loi = res.get("answer")
    if not tra_loi or not str(tra_loi).strip():
        return TRUOT, "câu trả lời rỗng (Body sẽ ném bad_response)"
    if "<think" in str(tra_loi):
        return TRUOT, "câu trả lời lộ thẻ <think>"
    if "mock_response" in str(tra_loi):
        return (TRUOT if can_model else MOCK), "câu trả lời của chế độ LOCAL, không có model thật"
    if giay > HAN_MAC_DINH_BODY_S:
        return CANH_BAO, (f"trả lời sau {giay:.0f}s, quá {HAN_MAC_DINH_BODY_S}s mặc định của Body: đặt BRAIN_CHAT_TIMEOUT_MS≥240000 hoặc "
                          "hâm nóng Brain bằng offline_training/bat_lai_brain.py trước khi khách ngồi xem")
    return DAT, f"trả lời {len(str(tra_loi))} ký tự sau {giay:.1f}s"


def node_dung_duoc(phien_ban: str) -> bool:
    """`node --version` ("v24.15.0"): từ 22.18 (hoặc 23.6) Node tự gỡ kiểu TypeScript; bản cũ hơn cần cờ thử nghiệm nên không dùng."""
    try:
        chinh, phu = (int(x) for x in phien_ban.strip().lstrip("v").split(".")[:2])
    except ValueError:
        return False
    return chinh >= 24 or (chinh == 23 and phu >= 6) or (chinh == 22 and phu >= 18)


def kiem_brain_ts(ket: Any, can_model: bool, co_token: bool) -> Chi:
    """Kết quả chạy CHÍNH brain.ts của Body (`chay_brain_ts.mts`): Body có đọc được câu trả lời của Brain không."""
    if not isinstance(ket, dict):
        return TRUOT, "runner không in ra JSON"
    mau: list[Chi] = []

    def buoc(ten: str) -> dict[str, Any]:
        v = ket.get(ten)
        return v if isinstance(v, dict) else {}

    h, bc, tk, ts, ch = buoc("health"), buoc("report"), buoc("ton_kho"), buoc("token_sai"), buoc("chat")
    if not h.get("ok") or h.get("degraded") or (co_token and h.get("auth_enabled") is not True):
        mau.append((TRUOT, f"checkBrainHealth: ok={h.get('ok')} degraded={h.get('degraded')} auth_enabled={h.get('auth_enabled')} {h.get('loi', '')}".strip()))
    if not bc.get("ok") or bc.get("so_ky") != 2 or bc.get("lai_gop_10") != 3_600_000 or bc.get("phu_gia_von") != 81.5:
        mau.append((TRUOT, f"buildReport: ok={bc.get('ok')} so_ky={bc.get('so_ky')} lai_gop_10={bc.get('lai_gop_10')} phu={bc.get('phu_gia_von')} {bc.get('loi', '')}".strip()))
    if not tk.get("ok") or tk.get("so_dong") != SO_DONG_TON_KHO or set(tk.get("ma") or []) != MA_TON_KHO_CO_LOI:
        mau.append((TRUOT, f"importInventoryFile: ok={tk.get('ok')} so_dong={tk.get('so_dong')} so_phat_hien={tk.get('so_phat_hien')} "
                           f"bo_qua={tk.get('ly_do_bo_qua')!r} {tk.get('loi', '')}".strip()))
    if co_token and (not ts.get("ok") or ts.get("kind_nhan_duoc") != "unauthorized"):
        mau.append((TRUOT, f"token sai: Body nhận kiểu lỗi {ts.get('kind_nhan_duoc')!r} (phải 'unauthorized' để hiện 'BRAIN_API_TOKEN sai hoặc thiếu')"))
    if not ch.get("ok"):
        mau.append((TRUOT, f"askBrain: {ch.get('kind')} {ch.get('loi', '')}".strip()))
    else:
        mau.append(kiem_chat({"status": "completed", "result": {"answer": ch.get("tra_loi")}}, float(ch.get("giay") or 0), can_model))
    for xau in (TRUOT, MOCK, CANH_BAO):
        loi = [ct for tt, ct in mau if tt == xau]
        if loi:
            return xau, "; ".join(loi)
    return DAT, "health, báo cáo, nạp tồn kho, lỗi token sai và chat đều đọc được qua mã thật của Body"


def chay_brain_ts(url: str, token: str, brain_ts: str, han_chat_s: float, file_ton_kho: Path) -> Any:
    """Tải (hoặc đọc) brain.ts, đặt cạnh runner trong thư mục tạm riêng, chạy bằng Node với quyền chỉ ĐỌC hai nơi cần thiết."""
    import shutil

    node = shutil.which("node")
    if not node:
        raise RuntimeError("không có `node` trong PATH (cần Node >= 22.18)")
    ver = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
    if not node_dung_duoc(ver):
        raise RuntimeError(f"Node {ver} quá cũ để chạy TypeScript trực tiếp (cần >= 22.18 hoặc 24)")
    if brain_ts:
        ma_nguon = Path(brain_ts).read_text(encoding="utf-8")
    else:
        from offline_training.doi_chieu_hop_dong_body import tai_brain_ts

        ma_nguon = tai_brain_ts(None)
    with tempfile.TemporaryDirectory(prefix="anser_brain_ts_") as tam:
        thu_muc = Path(tam)
        (thu_muc / "brain.ts").write_text(ma_nguon, encoding="utf-8")
        runner = thu_muc / "chay_brain_ts.mts"
        runner.write_text((ROOT / "offline_training" / "chay_brain_ts.mts").read_text(encoding="utf-8"), encoding="utf-8")
        moi_truong = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE")}
        moi_truong.update({"BRAIN_URL": url, "BRAIN_CHAT_TIMEOUT_MS": str(int(han_chat_s * 1000))})
        if token:
            moi_truong["BRAIN_API_TOKEN"] = token
        # Mã tải về là dữ liệu từ ngoài: Node 22.13+ có `--permission` — chỉ cho ĐỌC thư mục tạm và tệp mẫu; không ghi, không tạo tiến trình con.
        lenh = [node, "--no-warnings", "--permission", f"--allow-fs-read={thu_muc}", f"--allow-fs-read={file_ton_kho}", str(runner), str(file_ton_kho)]
        r = subprocess.run(lenh, cwd=thu_muc, env=moi_truong, capture_output=True, text=True, encoding="utf-8", timeout=han_chat_s + 120)
    dong = [x for x in r.stdout.strip().splitlines() if x.startswith("{")]
    if r.returncode != 0 or not dong:
        raise RuntimeError(f"node thoát {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
    return json.loads(dong[-1])


# ----------------------------------------------------------------------------------------------------------------------------
# Phần HTTP (stdlib, không thêm phụ thuộc). Mô phỏng `authHeaders()` và `uploadToBrain()` của brain.ts.
# ----------------------------------------------------------------------------------------------------------------------------
class Brain:
    def __init__(self, url: str, token: str = "", han: float = 30.0):
        self.url, self.token, self.han = url.rstrip("/"), token, han

    def _dau(self, json_body: bool, dinh_danh: bool, token: Optional[str]) -> dict[str, str]:
        dau = {"Content-Type": "application/json"} if json_body else {}
        t = self.token if token is None else token
        if t:
            dau["X-API-Token"] = t
        if dinh_danh:
            dau["X-User-Id"], dau["X-Store-Id"] = USER_ID, STORE_ID
        return dau

    def goi(self, method: str, duong: str, than: Any = None, *, dinh_danh: bool = False, token: Optional[str] = None,
            han: Optional[float] = None, multipart: Optional[tuple[str, bytes]] = None) -> tuple[int, Any]:
        byte: Optional[bytes]
        if multipart is not None:
            ten, noi_dung = multipart
            bien = "----kiemtichhop" + uuid.uuid4().hex
            byte = (f"--{bien}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{ten}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
                + noi_dung + f"\r\n--{bien}--\r\n".encode()
            dau = self._dau(False, dinh_danh, token)
            dau["Content-Type"] = f"multipart/form-data; boundary={bien}"     # ở đây phải đặt (urllib không tự sinh); fetch của Body tự sinh
        else:
            byte = json.dumps(than).encode() if than is not None else None
            dau = self._dau(than is not None, dinh_danh, token)
        req = urllib.request.Request(self.url + duong, data=byte, headers=dau, method=method)
        try:
            with urllib.request.urlopen(req, timeout=han or self.han) as r:  # noqa: S310 (địa chỉ do người chạy đưa)
                tho = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(tho) if tho else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:200]
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            return 0, f"{type(e).__name__}: {e}"[:200]


def chat_cho_xong(b: Brain, han_s: float) -> tuple[Any, float]:
    """Y như `askBrain`: POST /chat lấy task_id rồi hỏi /api/v1/task/{id} cách nhau 1–2 giây. Trả (task cuối, số giây)."""
    t0 = time.perf_counter()
    ma, acc = b.goi("POST", "/chat", {"user_id": USER_ID, "store_id": STORE_ID, "message": CAU_CHAT}, dinh_danh=True, han=han_s)
    if ma != 200 or not isinstance(acc, dict) or not acc.get("task_id"):
        return {"status": "failed", "error": f"/chat http={ma} {acc!r}"[:160]}, time.perf_counter() - t0
    task: Any = None
    while time.perf_counter() - t0 < han_s:
        time.sleep(1.0)
        ma, task = b.goi("GET", f"/api/v1/task/{acc['task_id']}", dinh_danh=True, han=15.0)
        if isinstance(task, dict) and task.get("status") in ("completed", "failed"):
            break
    return (task if isinstance(task, dict) else {"status": "processing"}), time.perf_counter() - t0


def chay_kiem(b: Brain, workspace: str, *, can_model: bool, bo_chat: bool, han_chat_s: float,
              voi_brain_ts: bool = False, brain_ts_file: str = "") -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="anser_mau_") as tam:
        return _chay_kiem(b, workspace, ghi_xlsx(Path(tam) / "ton_kho_mau.xlsx"), can_model=can_model, bo_chat=bo_chat,
                          han_chat_s=han_chat_s, voi_brain_ts=voi_brain_ts, brain_ts_file=brain_ts_file)


def _chay_kiem(b: Brain, workspace: str, file_ton_kho: Path, *, can_model: bool, bo_chat: bool, han_chat_s: float,
               voi_brain_ts: bool, brain_ts_file: str) -> list[dict[str, Any]]:
    ra: list[dict[str, Any]] = []

    def buoc(ten: str, bat_buoc: bool, f: Callable[[], Chi]) -> None:
        t0 = time.perf_counter()
        try:
            tt, ct = f()
        except Exception as e:  # noqa: BLE001 — một bước hỏng không được làm mất kết quả các bước khác; lỗi hiện nguyên trong bảng
            tt, ct = TRUOT, f"ngoại lệ {type(e).__name__}: {str(e)[:120]}"
        ra.append({"ten": ten, "trang_thai": tt, "bat_buoc": bat_buoc, "chi_tiet": ct, "giay": round(time.perf_counter() - t0, 2)})

    ma_h, health = b.goi("GET", "/health", han=15.0)
    if ma_h == 0 or not isinstance(health, dict):
        return [{"ten": "noi_duoc_brain", "trang_thai": TRUOT, "bat_buoc": True, "giay": 0.0,
                 "chi_tiet": f"GET /health → {health!r}. Kiểm BRAIN_URL (tên máy {urllib.parse.urlparse(b.url).hostname}), đường hầm, Brain đã chạy chưa"}]
    buoc("suc_khoe", True, lambda: kiem_suc_khoe(health))
    buoc("truong_body_doc", True, lambda: kiem_truong_body_doc(health))

    def xac_thuc() -> Chi:
        duong, than = "/tools/vat", VAT_VAO
        ma_khong, _ = b.goi("POST", duong, than, token="")
        ma_sai, _ = b.goi("POST", duong, than, token="sai-" + "x" * 8)
        ma_dung, _ = b.goi("POST", duong, than)
        return kiem_xac_thuc(bool(b.token), health.get("auth_enabled"), ma_khong, ma_sai, ma_dung)

    buoc("xac_thuc", True, xac_thuc)
    buoc("vat", True, lambda: kiem_vat(b.goi("POST", "/tools/vat", VAT_VAO)[1]))
    buoc("bao_gia", True, lambda: kiem_bao_gia(b.goi("POST", "/tools/quote", QUOTE_VAO)[1]))
    buoc("bao_cao", True, lambda: kiem_bao_cao(b.goi("POST", "/tools/report", BAO_CAO_VAO)[1]))
    buoc("bao_cao_thieu_gia_von", True, lambda: kiem_bao_cao_thieu_gia_von(
        b.goi("POST", "/tools/report", BAO_CAO_KHONG_GIA_VON)[1], b.goi("POST", "/tools/report", BAO_CAO_CHI_CO_CHI_PHI)[1]))

    def ton_kho() -> Chi:
        ma, r = b.goi("POST", "/tools/inventory-import", multipart=(file_ton_kho.name, file_ton_kho.read_bytes()), han=60.0)
        return kiem_ton_kho(r) if ma == 200 else (TRUOT, f"http={ma} {r!r}"[:160])

    buoc("ton_kho_nap_file", True, ton_kho)

    def kho_tri_thuc() -> Chi:
        ma, r = b.goi("GET", "/knowledge/documents?" + urllib.parse.urlencode({"workspace_id": workspace}))
        return kiem_kho_tri_thuc(ma, r, health.get("kb_ready"))

    buoc("kho_tri_thuc", False, kho_tri_thuc)
    if bo_chat:
        ra.append({"ten": "chat", "trang_thai": BO_QUA, "bat_buoc": False, "chi_tiet": "bị tắt bằng --bo-chat", "giay": 0.0})
    else:
        def chat() -> Chi:
            task, giay = chat_cho_xong(b, han_chat_s)
            return kiem_chat(task, giay, can_model)

        buoc("chat", True, chat)
    if voi_brain_ts:
        # Bắt buộc khi người chạy đã xin: yêu cầu mà không chạy được thì phải TRƯỢT to, không được lặng lẽ bỏ qua (`noi_duoc_brain` ở trên đã cắt sớm nếu Brain chết).
        buoc("brain_ts_cua_body", True, lambda: kiem_brain_ts(
            chay_brain_ts(b.url, b.token, brain_ts_file, han_chat_s, file_ton_kho), can_model, bool(b.token)))
    return ra


def ket_luan(ra: list[dict[str, Any]]) -> tuple[int, str]:
    if any(k["ten"] == "noi_duoc_brain" for k in ra):
        return 2, "KHÔNG NỐI ĐƯỢC BRAIN"
    if any(k["bat_buoc"] and k["trang_thai"] == TRUOT for k in ra):
        return 1, "KHÔNG ĐẠT"
    if any(k["trang_thai"] == MOCK for k in ra):
        return 0, "ĐẠT phần tất định; chat còn là mock (chưa có model)"
    return 0, "ĐẠT"


def in_bang(ra: list[dict[str, Any]], kl: str) -> None:
    nhan = {DAT: "ĐẠT   ", TRUOT: "TRƯỢT ", MOCK: "MOCK  ", CANH_BAO: "CẢNH BÁO", BO_QUA: "BỎ QUA "}
    for k in ra:
        print(f"  {nhan[k['trang_thai']]:9}{k['ten']:<24}{k['giay']:>6.1f}s  {k['chi_tiet']}")
    print(kl)


# ----------------------------------------------------------------------------------------------------------------------------
def tu_bat(han_khoi_dong: float):
    """Bật `uvicorn src.api.main:app` ở ENV=LOCAL với token tạm; trả (tiến trình, url, đường log)."""
    cong = cong_trong()
    moi_truong = {**os.environ, "ENV": "LOCAL", "PYTHONUTF8": "1", "API_AUTH_TOKEN": KHOA_TAM, "API_HMAC_MODE": "off"}
    moi_truong.pop("DATABASE_URL", None)
    log = Path(tempfile.gettempdir()) / "anser_kiem_tich_hop_body.log"      # ngoài repo: không bao giờ bị commit
    f = open(log, "w", encoding="utf-8")  # noqa: SIM115 — đóng khi tiến trình dừng, ở `main`
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.api.main:app", "--port", str(cong), "--log-level", "warning"],
                         cwd=ROOT, env=moi_truong, stdout=f, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{cong}"
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < han_khoi_dong and p.poll() is None:
        if Brain(url).goi("GET", "/health", han=3.0)[0] == 200:
            break
        time.sleep(0.5)
    return p, url, log, f


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("BRAIN_URL", ""), help="địa chỉ Brain (mặc định: biến BRAIN_URL, như Body)")
    ap.add_argument("--tu-bat", action="store_true", help="bật Brain LOCAL (không GPU) với token tạm rồi kiểm; bỏ qua --url")
    ap.add_argument("--workspace", default=os.environ.get("BRAIN_KB_WORKSPACE", "default"), help="phạm vi kho tri thức (mặc định: BRAIN_KB_WORKSPACE, như Body)")
    ap.add_argument("--can-model", action="store_true", help="chat PHẢI do model thật sinh; câu mock là TRƯỢT (dùng ngay trước buổi demo)")
    ap.add_argument("--bo-chat", action="store_true", help="bỏ bước chat (kiểm riêng phần tất định)")
    ap.add_argument("--voi-brain-ts", action="store_true",
                    help="chạy thêm CHÍNH brain.ts của Body (tải từ repo Body) bằng Node >= 22.18: chứng minh Body ĐỌC được câu trả lời của Brain")
    ap.add_argument("--brain-ts-file", default="", help="với --voi-brain-ts: đọc brain.ts từ đĩa thay vì tải về (ví dụ nhánh Body chưa gộp)")
    ap.add_argument("--han-chat", type=float, default=240.0, help="số giây chờ câu chat đầu (Brain nguội mất 1–3 phút; mặc định 240)")
    ap.add_argument("--han-khoi-dong", type=float, default=60.0, help="với --tu-bat: số giây chờ server lên")
    ap.add_argument("--json", dest="json_ra", default="", help="ghi kết quả máy đọc được ra đường dẫn này")
    a = ap.parse_args(argv)

    proc = f = None
    token = os.environ.get("BRAIN_API_TOKEN", "")
    url, ghi_chu = a.url, ""
    if a.tu_bat:
        proc, url, log, f = tu_bat(a.han_khoi_dong)
        token, ghi_chu = KHOA_TAM, f"Brain LOCAL tự bật, log: {log}"
    if not url:
        print("Thiếu địa chỉ Brain: đặt BRAIN_URL (và BRAIN_API_TOKEN, BRAIN_KB_WORKSPACE như bên Body) hoặc dùng --tu-bat.", file=sys.stderr)
        return 2
    try:
        ra = chay_kiem(Brain(url, token), a.workspace, can_model=a.can_model, bo_chat=a.bo_chat, han_chat_s=a.han_chat,
                       voi_brain_ts=a.voi_brain_ts, brain_ts_file=a.brain_ts_file)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if f is not None:
            f.close()
    ma_thoat, kl = ket_luan(ra)
    print(f"Brain: {urllib.parse.urlparse(url).hostname}  {ghi_chu}".rstrip())
    in_bang(ra, kl)
    if a.json_ra:
        Path(a.json_ra).write_text(json.dumps({"ket_luan": kl, "ma_thoat": ma_thoat, "kiem": ra}, ensure_ascii=False, indent=1), encoding="utf-8")
    return ma_thoat


if __name__ == "__main__":
    sys.exit(main())
