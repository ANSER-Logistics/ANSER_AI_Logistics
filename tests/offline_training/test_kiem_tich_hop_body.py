"""
tests/offline_training/test_kiem_tich_hop_body.py — phần THUẦN của `offline_training/kiem_tich_hop_body.py`.

Việc bật Brain thật chạy bằng `python offline_training/kiem_tich_hop_body.py --tu-bat` (không ở pytest: bật tiến trình con làm bộ test chập chờn).
Ở đây khoá phép chấm: mỗi phép phải ĐỎ khi một phản hồi sai, không chỉ xanh khi mọi thứ đúng — công cụ chỉ biết xanh thì demo hỏng mà vẫn thấy "đạt".
"""

from __future__ import annotations

import copy

import pytest

from offline_training import kiem_tich_hop_body as k

HEALTH_TOT = {"status": "ok", "degraded": False, "engine_ready": True, "vision_ready": True, "auth_enabled": True, "kb_ready": True}

BAO_CAO_TOT = {
    "periods": [
        {"period": "2026-09", "revenue": 10_000_000, "gross_profit": 3_000_000, "net_profit": 3_000_000},
        {"period": "2026-10", "revenue": 17_000_000, "gross_profit": 3_600_000, "net_profit": 1_600_000},
    ],
    "products": [{"product": "Dầu AW46", "missing_cogs": False, "gross_profit": 6_600_000},
                 {"product": "Mỡ chịu nhiệt", "missing_cogs": True, "gross_profit": None}],
    "explain": {"cogs_coverage_pct": 81.5, "confidence": "trung bình", "formula": "f", "period_count": 2},
}
CO_DOANH_THU = {"explain": {"cogs_coverage_pct": 0.0, "confidence": "thấp", "formula": "f", "period_count": 1}, "warnings": ["Chỉ 0% doanh thu có giá vốn"]}
CHI_CO_CHI_PHI = {"explain": {"cogs_coverage_pct": None, "confidence": "không có dữ liệu", "formula": "f", "period_count": 1}, "warnings": ["x"]}

TON_KHO_TOT = {"import": {"rows_parsed": k.SO_DONG_TON_KHO},
               "audit": {"findings": [{"code": c} for c in sorted(k.MA_TON_KHO_CO_LOI)] + [{"code": "DN-TL-200"}]},
               "audit_skipped_reason": None}


def _trang_thai(kq):
    return kq[0]


# --- sức khoẻ ----------------------------------------------------------------------------------------------------------------
def test_suc_khoe_tot_va_ba_cach_hong():
    assert _trang_thai(k.kiem_suc_khoe(HEALTH_TOT)) == k.DAT
    assert _trang_thai(k.kiem_suc_khoe({**HEALTH_TOT, "status": "loading"})) == k.TRUOT
    assert _trang_thai(k.kiem_suc_khoe({**HEALTH_TOT, "degraded": True})) == k.TRUOT      # Brain tụt degraded: không demo
    assert _trang_thai(k.kiem_suc_khoe("Bad Gateway")) == k.TRUOT                           # đường hầm trả trang HTML lỗi


def test_truong_body_doc_thieu_auth_enabled_la_hong():
    assert _trang_thai(k.kiem_truong_body_doc(HEALTH_TOT)) == k.DAT
    for khoa in ("engine_ready", "vision_ready", "auth_enabled"):
        h = {a: b for a, b in HEALTH_TOT.items() if a != khoa}
        assert _trang_thai(k.kiem_truong_body_doc(h)) == k.TRUOT, khoa


# --- xác thực ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("khong,sai,dung,mong", [
    (401, 401, 200, k.DAT),
    (403, 401, 200, k.DAT),
    (200, 401, 200, k.TRUOT),     # không token mà vào được
    (401, 200, 200, k.TRUOT),     # token sai mà vào được
    (401, 401, 401, k.TRUOT),     # BRAIN_API_TOKEN lệch API_AUTH_TOKEN
    (401, 401, 0, k.TRUOT),
])
def test_xac_thuc_co_token(khong, sai, dung, mong):
    assert _trang_thai(k.kiem_xac_thuc(True, True, khong, sai, dung)) == mong


def test_xac_thuc_dua_token_ma_brain_khong_kiem_la_hong():
    """Đã đặt BRAIN_API_TOKEN bên Body nhưng Brain báo auth_enabled=false: biến bên Brain bị đặt sai tên, Brain mở toang."""
    assert _trang_thai(k.kiem_xac_thuc(True, False, 200, 200, 200)) == k.TRUOT
    assert _trang_thai(k.kiem_xac_thuc(True, None, 200, 200, 200)) == k.TRUOT            # Brain cũ không có trường này


def test_xac_thuc_khong_token():
    assert _trang_thai(k.kiem_xac_thuc(False, False, 200, 200, 200)) == k.CANH_BAO       # LOCAL: chấp nhận được, nhưng phải nói ra
    assert _trang_thai(k.kiem_xac_thuc(False, True, 401, 401, 401)) == k.TRUOT           # Brain đòi token mà ta không có


# --- công cụ tất định --------------------------------------------------------------------------------------------------------
def test_vat_va_bao_gia_dung_dap_an_tinh_tay():
    assert _trang_thai(k.kiem_vat({"calculated_total": 2_200_000, "is_valid": True})) == k.DAT
    assert _trang_thai(k.kiem_vat({"calculated_total": 2_160_000, "is_valid": True})) == k.TRUOT
    assert _trang_thai(k.kiem_vat({"calculated_total": 2_200_000, "is_valid": False})) == k.TRUOT
    assert _trang_thai(k.kiem_vat("Internal Server Error")) == k.TRUOT
    assert _trang_thai(k.kiem_bao_gia({"quote": {"quoted_price": 1_139_000}})) == k.DAT
    assert _trang_thai(k.kiem_bao_gia({"quote": {"quoted_price": 1_138_500}})) == k.TRUOT   # quên làm tròn tới nghìn
    assert _trang_thai(k.kiem_bao_gia(None)) == k.TRUOT


def test_bao_cao_tot_va_tung_loi():
    assert _trang_thai(k.kiem_bao_cao(BAO_CAO_TOT)) == k.DAT

    def sua(duong, gia_tri):
        r = copy.deepcopy(BAO_CAO_TOT)
        dich = r
        for p in duong[:-1]:
            dich = dich[p]
        dich[duong[-1]] = gia_tri
        return r

    sai = [
        sua(("periods", 1, "gross_profit"), 8_600_000),            # tính lãi gộp trên CẢ doanh thu thay vì phần có giá vốn
        sua(("periods", 1, "net_profit"), 3_600_000),             # quên trừ chi phí
        sua(("explain", "cogs_coverage_pct"), 100.0),
        sua(("products", 1, "gross_profit"), 0),                  # điền 0 cho hàng chưa có giá vốn
        sua(("products", 1, "missing_cogs"), False),
    ]
    for r in sai:
        assert _trang_thai(k.kiem_bao_cao(r)) == k.TRUOT, r
    for khoa in ("cogs_coverage_pct", "confidence", "formula", "period_count"):
        r = copy.deepcopy(BAO_CAO_TOT)
        del r["explain"][khoa]
        assert _trang_thai(k.kiem_bao_cao(r)) == k.TRUOT, khoa


def test_bao_cao_thieu_gia_von_hai_nhanh_khac_nhau():
    assert _trang_thai(k.kiem_bao_cao_thieu_gia_von(CO_DOANH_THU, CHI_CO_CHI_PHI)) == k.DAT
    # "Sửa cho giống nhau" là đúng lỗi AGENTS R1 cấm: mỗi nhánh một câu trả lời, đảo đi là đỏ.
    assert _trang_thai(k.kiem_bao_cao_thieu_gia_von(CHI_CO_CHI_PHI, CO_DOANH_THU)) == k.TRUOT
    mat_khoa = copy.deepcopy(CHI_CO_CHI_PHI)
    del mat_khoa["explain"]["confidence"]
    assert _trang_thai(k.kiem_bao_cao_thieu_gia_von(CO_DOANH_THU, mat_khoa)) == k.TRUOT
    khong_canh_bao = {**CO_DOANH_THU, "warnings": []}
    assert _trang_thai(k.kiem_bao_cao_thieu_gia_von(khong_canh_bao, CHI_CO_CHI_PHI)) == k.TRUOT
    tin_cay_cao = copy.deepcopy(CO_DOANH_THU)
    tin_cay_cao["explain"]["confidence"] = "cao"
    assert _trang_thai(k.kiem_bao_cao_thieu_gia_von(tin_cay_cao, CHI_CO_CHI_PHI)) == k.TRUOT


def test_ton_kho_bay_ma_co_loi_khong_hon_khong_kem():
    assert _trang_thai(k.kiem_ton_kho(TON_KHO_TOT)) == k.DAT
    thieu = copy.deepcopy(TON_KHO_TOT)
    thieu["audit"]["findings"] = [f for f in thieu["audit"]["findings"] if f["code"] != "MO-EP2-15"]
    assert _trang_thai(k.kiem_ton_kho(thieu)) == k.TRUOT                                  # bỏ sót một mã gieo sẵn
    oan = copy.deepcopy(TON_KHO_TOT)
    oan["audit"]["findings"].append({"code": "DN-SG-18"})
    assert _trang_thai(k.kiem_ton_kho(oan)) == k.TRUOT                                    # gắn cờ oan một mã sạch
    doc_thieu = copy.deepcopy(TON_KHO_TOT)
    doc_thieu["import"]["rows_parsed"] = k.SO_DONG_TON_KHO - 1
    assert _trang_thai(k.kiem_ton_kho(doc_thieu)) == k.TRUOT
    bo_qua_kiem = {**TON_KHO_TOT, "audit": None, "audit_skipped_reason": "đọc file không chắc chắn"}
    assert _trang_thai(k.kiem_ton_kho(bo_qua_kiem)) == k.TRUOT                            # audit=null KHÔNG phải "không có lỗi"


# --- kho tri thức và chat ----------------------------------------------------------------------------------------------------
def test_kho_tri_thuc_chua_san_sang_la_canh_bao_khong_chan_demo():
    assert _trang_thai(k.kiem_kho_tri_thuc(200, {"documents": []}, True)) == k.DAT
    assert _trang_thai(k.kiem_kho_tri_thuc(200, {"documents": []}, False)) == k.CANH_BAO
    assert _trang_thai(k.kiem_kho_tri_thuc(503, "kb not ready", False)) == k.CANH_BAO


def _task(cau, trang_thai="completed"):
    return {"status": trang_thai, "result": {"answer": cau}}


def test_chat_cac_truong_hop():
    assert _trang_thai(k.kiem_chat(_task("Chào bạn, mình giúp được việc kho."), 3.0, True)) == k.DAT
    assert _trang_thai(k.kiem_chat(_task(""), 3.0, True)) == k.TRUOT                       # Body sẽ ném bad_response
    assert _trang_thai(k.kiem_chat(_task("<think>nghĩ</think>ok"), 3.0, True)) == k.TRUOT
    assert _trang_thai(k.kiem_chat({"status": "failed", "error": "boom"}, 3.0, True)) == k.TRUOT
    assert _trang_thai(k.kiem_chat({"status": "processing"}, 240.0, True)) == k.TRUOT
    assert _trang_thai(k.kiem_chat(None, 1.0, True)) == k.TRUOT
    # Chậm nhưng đúng: chỉ là cảnh báo vì Body mặc định chờ 60 giây.
    assert _trang_thai(k.kiem_chat(_task("ok"), 75.0, True)) == k.CANH_BAO


def test_chat_mock_chi_dat_khi_khong_doi_model_that():
    mock = _task('{"mock_response": "LOCAL mock chat response."}')
    assert _trang_thai(k.kiem_chat(mock, 1.0, False)) == k.MOCK
    assert _trang_thai(k.kiem_chat(mock, 1.0, True)) == k.TRUOT                            # --can-model: mock KHÔNG được tính là đạt


# --- kết luận ----------------------------------------------------------------------------------------------------------------
def _b(ten, trang_thai, bat_buoc=True):
    return {"ten": ten, "trang_thai": trang_thai, "bat_buoc": bat_buoc, "chi_tiet": "", "giay": 0.0}


def test_ket_luan_ma_thoat():
    assert k.ket_luan([_b("a", k.DAT), _b("b", k.CANH_BAO, False)])[0] == 0
    assert k.ket_luan([_b("a", k.DAT), _b("b", k.MOCK)])[0] == 0 and "mock" in k.ket_luan([_b("b", k.MOCK)])[1]
    assert k.ket_luan([_b("a", k.DAT), _b("b", k.TRUOT)])[0] == 1
    assert k.ket_luan([_b("a", k.TRUOT, False)])[0] == 0                                   # bước không bắt buộc trượt không chặn
    assert k.ket_luan([_b("noi_duoc_brain", k.TRUOT)])[0] == 2                             # không nối được: không có gì để kết luận


def test_dinh_danh_la_uuid_nhu_body_va_khong_doi_giua_cac_lan_chay():
    import uuid

    assert str(uuid.UUID(k.USER_ID)) == k.USER_ID and str(uuid.UUID(k.STORE_ID)) == k.STORE_ID and k.USER_ID != k.STORE_ID


def test_tep_mau_ton_kho_do_cong_cu_tu_sinh_va_khop_so_lieu_trong_tai_lieu(tmp_path):
    """Tệp .xlsx không được commit (gitignore): công cụ tự sinh. Tài liệu demo nói "11 mã, bảy mã có lỗi"; đổi bộ sinh là phải sửa tài liệu."""
    from sample_data.make_sample_data import ghi_xlsx

    f = ghi_xlsx(tmp_path / "ton_kho_mau.xlsx")
    assert f.exists() and f.stat().st_size > 0
    assert (k.SO_DONG_TON_KHO, len(k.MA_TON_KHO_CO_LOI)) == (11, 7)


# --- chạy chính brain.ts của Body --------------------------------------------------------------------------------------------
KET_TS_TOT = {
    "health": {"ok": True, "degraded": False, "auth_enabled": True, "engine_ready": True, "vision_ready": True},
    "report": {"ok": True, "so_ky": 2, "lai_gop_10": 3_600_000, "phu_gia_von": 81.5, "tin_cay": "trung bình"},
    "ton_kho": {"ok": True, "so_dong": k.SO_DONG_TON_KHO, "so_phat_hien": 8, "ma": sorted(k.MA_TON_KHO_CO_LOI), "ly_do_bo_qua": None},
    "token_sai": {"ok": True, "kind_nhan_duoc": "unauthorized", "status": 401},
    "chat": {"ok": True, "giay": 3.0, "tra_loi": "Chào bạn, mình giúp được việc kho.", "do_dai": 34},
}


def _ts(sua=None, can_model=True, co_token=True):
    ket = copy.deepcopy(KET_TS_TOT)
    for duong, gia_tri in (sua or {}).items():
        buoc, khoa = duong
        ket[buoc][khoa] = gia_tri
    return k.kiem_brain_ts(ket, can_model, co_token)


def test_brain_ts_tot_va_tung_cho_hong():
    assert _trang_thai(_ts()) == k.DAT
    sai = [
        {("health", "ok"): False},
        {("health", "auth_enabled"): False},                       # Brain mở toang dù đã đưa token
        {("report", "lai_gop_10"): 8_600_000},
        {("report", "phu_gia_von"): 100.0},
        {("ton_kho", "ma"): ["DN-TL-200"]},
        {("token_sai", "kind_nhan_duoc"): "server_error"},         # Body không nhận ra 401: sẽ hiện lỗi chung thay vì "token sai"
        {("token_sai", "kind_nhan_duoc"): "KHONG_LOI"},            # token sai mà vẫn vào được
        {("chat", "ok"): False},
        {("chat", "tra_loi"): ""},
    ]
    for sua in sai:
        assert _trang_thai(_ts(sua)) == k.TRUOT, sua


def test_brain_ts_chat_mock_va_cham_khong_dat_im_lang():
    mock = {("chat", "tra_loi"): '{"mock_response": "LOCAL mock chat response."}'}
    assert _trang_thai(_ts(mock, can_model=False)) == k.MOCK
    assert _trang_thai(_ts(mock, can_model=True)) == k.TRUOT
    assert _trang_thai(_ts({("chat", "giay"): 90.0})) == k.CANH_BAO


def test_brain_ts_khong_token_thi_khong_doi_unauthorized():
    """Brain LOCAL không đòi token: không có gì để so, nên kind 'KHONG_LOI' là bình thường chứ không phải lỗi."""
    sua = {("token_sai", "kind_nhan_duoc"): "KHONG_LOI", ("health", "auth_enabled"): False}
    assert _trang_thai(_ts(sua, co_token=False)) == k.DAT


def test_brain_ts_runner_khong_in_ra_json_la_truot_khong_no():
    assert _trang_thai(k.kiem_brain_ts(None, True, True)) == k.TRUOT
    assert _trang_thai(k.kiem_brain_ts({}, True, True)) == k.TRUOT


@pytest.mark.parametrize("ver,mong", [
    ("v24.15.0", True), ("v22.18.0", True), ("v22.20.1", True), ("v23.6.0", True),
    ("v22.17.9", False), ("v23.5.0", False), ("v20.9.0", False), ("v18.0.0", False), ("rác", False), ("", False),
])
def test_phien_ban_node_du_de_chay_typescript_truc_tiep(ver, mong):
    assert k.node_dung_duoc(ver) is mong


def test_runner_chi_dung_ham_cua_body_va_khong_import_goi_nao():
    """Runner là mã chạy cạnh brain.ts tải từ ngoài: chỉ được `node:fs` và `./brain.ts`; thêm import là mở rộng bề mặt tin cậy."""
    import re

    nguon = (k.ROOT / "offline_training" / "chay_brain_ts.mts").read_text(encoding="utf-8")
    cac_import = set(re.findall(r'from\s+"([^"]+)"', nguon))
    assert cac_import == {"node:fs", "./brain.ts"}, cac_import
