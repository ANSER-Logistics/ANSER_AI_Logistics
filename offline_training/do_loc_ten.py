"""
offline_training/do_loc_ten.py — ĐO lớp lọc tên khách trong truy vấn web (`retrieval_policy._xoa_ten_rieng`) trên kho câu hỏi của repo (A9, brain#327).

Hỏi một việc: trên các câu HỎI CÔNG KHAI có từ đánh dấu đối tác ("công ty", "khách hàng"...), luật hiện hành khác luật trước A9b (từ dừng đơn đa nghĩa như "thanh", "gia" chưa thành cụm dừng; A9, brain#327; A9b) ở bao nhiêu câu, và bao nhiêu câu bị CHẶN
(trả rỗng, không tra web) mà trước đó không bị. Đó là phần "chặn oan" của lớp tên. Không đo rò lọt: kho này không có nhãn tên khách.

KHO CÂU HỎI: `seed_prompts.jsonl` và câu của người dùng trong `v2_sources/*.jsonl`. Đều do dev viết hoặc sinh, KHÔNG phải nhật ký thật của khách. Nên số đo là cận trên lạc quan, và
mẫu nhỏ (vài chục câu): 0 trên 31 vẫn tương thích với tỉ lệ thật tới khoảng 10% (quy tắc ba). Đo thật là chế độ bóng trên câu hỏi thật (A6, #208).

CHẠY:  python -m offline_training.do_loc_ten
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from src.core import retrieval_policy as rp  # noqa: E402


def cau_hoi() -> list[str]:
    ra = [json.loads(d)["prompt"] for d in (GOC / "offline_training" / "seed_prompts.jsonl").read_text(encoding="utf-8").splitlines() if d.strip()]
    for f in sorted(glob.glob(str(GOC / "offline_training" / "v2_sources" / "*.jsonl"))):
        for d in Path(f).read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(d)
            except ValueError:
                continue
            ra += [m["content"] for m in obj.get("messages", []) if m.get("role") == "user" and isinstance(m.get("content"), str)]
    return ra


# Luật TRƯỚC A9b (23/11/2026) dựng lại từ luật hiện hành: âm tiết dễ làm tên còn là từ dừng đơn, năm cụm mô tả của A9b chưa có, chưa có cụm dừng.
A9B_TU_DUNG_BO = frozenset("thanh gia trung thành tài chính đại lý bảo thương tư nhân mai".split())
A9B_TU_DUNG_THEM_CU = frozenset({"đình", "hữu", "liên", "quan", "hiệu", "thường", "xuyên"}) | A9B_TU_DUNG_BO
A9B_CUM_MO_TA_MOI = {("hữu", "hạn"), ("tài", "chính"), ("bảo", "hiểm"), ("đại", "lý"), ("gia", "công")}
LUAT_TRUOC_A9B = dict(
    cum_mo_ta=tuple(c for c in rp._CUM_MO_TA if c not in A9B_CUM_MO_TA_MOI),
    cum_dung=(),
    tu_dung=frozenset(rp._TU_THONG_DUNG | A9B_TU_DUNG_THEM_CU),
)
LUAT_HIEN_HANH: dict = {}


def loc(q: str, luat: dict) -> str:
    try:
        return rp._xoa_ten_rieng(" ".join(q.split()), **luat)
    except rp._KhongLocSach:
        return ""


def do() -> dict:
    qs = cau_hoi()
    co_dau = [q for q in qs if any(rp._do_dai_danh_dau(q.split(), i) for i in range(len(q.split())))]
    cong_khai = [q for q in co_dau if rp.decide_web_fallback(q).allow]
    cap = [(q, loc(q, LUAT_TRUOC_A9B), loc(q, LUAT_HIEN_HANH)) for q in cong_khai]
    khac = [c for c in cap if c[1] != c[2]]
    chan_moi = [c for c in khac if c[2] == "" and c[1] != ""]
    return {"tong": len(qs), "co_tu_danh_dau": len(co_dau), "cong_khai_co_tu_danh_dau": len(cong_khai), "khac_nhau": khac, "chan_moi": chan_moi}


def main() -> None:
    r = do()
    print(f"Câu hỏi trong kho: {r['tong']}; có từ đánh dấu đối tác: {r['co_tu_danh_dau']}; trong đó câu CÔNG KHAI (sẽ tra web): {r['cong_khai_co_tu_danh_dau']}")
    n = r["cong_khai_co_tu_danh_dau"] or 1
    print(f"Khác luật cũ: {len(r['khac_nhau'])}/{n}; chặn mới (trả rỗng): {len(r['chan_moi'])}/{n}")
    for q, a, b in r["khac_nhau"][:20]:
        print(f"- {q[:100]}\n    cũ : {a[:100]}\n    mới: {b[:100]}")
    print("\nLưu ý: kho câu do dev viết, mẫu nhỏ; không phải nhật ký thật (xem docstring).")


if __name__ == "__main__":
    main()
