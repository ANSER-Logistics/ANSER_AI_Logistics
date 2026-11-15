"""
tests/test_n8n_bao_gia_nhanh_loi.py — workflow báo giá phải BÁO LỖI, không im lặng thử lại.

`logistics_quote_request.json` gọi Brain ở hai chỗ ("Chọn hãng xe (Brain)", "Tính báo giá
(Brain)"). Bản trước đặt `retryOnFail` (maxTries 2) cho cả hai và không có nhánh lỗi. Hai hậu quả:

  1. Lỗi 4xx của Brain KHÔNG tự khỏi — 422 vì giá dầu đã cũ từ 7 ngày, 422 vì thiếu tuyến /
     sai trường. Thử lại chỉ gửi đúng yêu cầu đó thêm một lần và nhận đúng lỗi đó thêm một lần.
     n8n không có cách "chỉ thử lại khi 5xx": `retryOnFail` thử lại MỌI lỗi. Nên tắt hẳn.
  2. Không có nhánh lỗi nên lỗi chỉ nằm trong lịch sử execution của n8n. Chủ doanh nghiệp —
     người nhắn báo giá khi đang lái xe — không biết báo giá không được tạo, và webhook gốc trả
     500 làm Brain nói "lỗi kết nối n8n" (sai: n8n vẫn sống, chính Brain mới từ chối).

Cách sửa: `onError: continueErrorOutput` trên hai node gọi Brain, cổng lỗi nối tới một node dựng
cảnh báo -> báo Discord chủ DN (cùng webhook với "Báo chủ DN duyệt") -> trả lời webhook gốc bằng
`{ok: false, ...}` KHÔNG có `draft_id`, để `chat.py::_handle_logistics_quote` (đã xử lý thiếu
draft_id) nói thật là "chưa xác nhận" thay vì tuyên bố đã tạo nháp.

Không có ngưỡng nào trong n8n (R4): node lỗi chỉ CHÉP lời của Brain, không tự phân loại "giá dầu
cũ" hay "tuyến thiếu".

Test KHÔNG thay được lần chạy thật trên n8n: cấu trúc `connections` và đoạn JS được kiểm ở đây,
còn hình dạng chính xác của `json.error` mà n8n đưa vào cổng lỗi thì phải có người có instance
n8n chạy thử (đoạn JS đã thử bốn hình dạng khác nhau vì lý do đó).

Test cần Node để chạy đoạn JS thật. Thiếu Node thì test ĐỎ (không skip): một test bị skip lặng lẽ
là một nhánh lỗi không ai kiểm.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parent.parent / "workflows" / "logistics" / "logistics_quote_request.json"

CHON_HANG = "Chọn hãng xe (Brain)"
TINH_GIA = "Tính báo giá (Brain)"
HAI_NODE_BRAIN = (CHON_HANG, TINH_GIA)

# 14 node gốc — phải còn nguyên.
NODE_GOC = {
    "Nhận yêu cầu báo giá", "Đọc Carriers", "Đọc CarrierQuotes", "Đọc PricingRules",
    "Đọc FuelIndex", "Đọc Routes", "Ghép dữ liệu", CHON_HANG, "Lấy hãng đầu bảng",
    TINH_GIA, "Dựng nháp + embed", "Lưu nháp vào Sheet", "Báo chủ DN duyệt",
    "Trả kết quả cho Brain",
}

# Đường thành công: mỗi node đầu ra 0 nối đúng node kế tiếp (như bản gốc).
DUONG_THANH_CONG = [
    ("Nhận yêu cầu báo giá", "Đọc Carriers"),
    ("Đọc Carriers", "Đọc CarrierQuotes"),
    ("Đọc CarrierQuotes", "Đọc PricingRules"),
    ("Đọc PricingRules", "Đọc FuelIndex"),
    ("Đọc FuelIndex", "Đọc Routes"),
    ("Đọc Routes", "Ghép dữ liệu"),
    ("Ghép dữ liệu", CHON_HANG),
    (CHON_HANG, "Lấy hãng đầu bảng"),
    ("Lấy hãng đầu bảng", TINH_GIA),
    (TINH_GIA, "Dựng nháp + embed"),
    ("Dựng nháp + embed", "Lưu nháp vào Sheet"),
    ("Lưu nháp vào Sheet", "Báo chủ DN duyệt"),
    ("Báo chủ DN duyệt", "Trả kết quả cho Brain"),
]

# Những node chỉ được chạy khi báo giá THÀNH CÔNG — nhánh lỗi mà chạm vào là tạo nháp giả.
NODE_CHI_CHO_THANH_CONG = {
    "Lấy hãng đầu bảng", "Dựng nháp + embed", "Lưu nháp vào Sheet",
    "Báo chủ DN duyệt", "Trả kết quả cho Brain",
}

DISCORD_URL = "={{ $env.DISCORD_WEBHOOK_URL }}"


def _wf() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def _node(wf: dict, ten: str) -> dict:
    n = next((n for n in wf["nodes"] if n["name"] == ten), None)
    assert n is not None, f"workflow không có node {ten!r}"
    return n


def _lien_ket(wf: dict, nguon: str, cong: int) -> list[str]:
    """Tên các node mà `nguon` nối tới ở cổng đầu ra `cong`. Rỗng nếu không có cổng đó."""
    outs = wf["connections"].get(nguon, {}).get("main", [])
    return [lk["node"] for lk in outs[cong]] if cong < len(outs) else []


def _den_duoc(wf: dict, bat_dau: list[str]) -> list[str]:
    """Mọi node đến được từ `bat_dau` (theo thứ tự gặp, kể cả bản thân), mọi cổng."""
    thay: list[str] = []
    hang = list(bat_dau)
    while hang:
        t = hang.pop(0)
        if t in thay:
            continue
        thay.append(t)
        for branch in wf["connections"].get(t, {}).get("main", []):
            hang.extend(lk["node"] for lk in branch)
    return thay


def _nhanh_loi(wf: dict) -> list[str]:
    """Các node đến được từ cổng lỗi (đầu ra 1) của hai node Brain."""
    goc = [t for b in HAI_NODE_BRAIN for t in _lien_ket(wf, b, 1)]
    return _den_duoc(wf, goc)


# ---------------------------------------------------------------------------
# Cấu trúc (không cần Node)
# ---------------------------------------------------------------------------

def test_ket_noi_hop_le_moi_node_dich_ton_tai():
    wf = _wf()
    ten = [n["name"] for n in wf["nodes"]]
    assert len(set(ten)) == len(ten), "trùng tên node"
    assert len({n["id"] for n in wf["nodes"]}) == len(wf["nodes"]), "trùng id node"
    for nguon, outs in wf["connections"].items():
        assert nguon in ten, f"connections từ node lạ {nguon!r}"
        for branch in outs["main"]:
            for lk in branch:
                assert lk["node"] in ten, f"{nguon!r} trỏ tới node không có: {lk['node']!r}"


@pytest.mark.parametrize("ten", HAI_NODE_BRAIN)
def test_node_brain_khong_con_thu_lai(ten):
    n = _node(_wf(), ten)
    # Thử lại chỉ có ích với lỗi mạng/5xx; 4xx (giá dầu cũ, thiếu tuyến, sai trường) không tự
    # khỏi. n8n không lọc theo mã lỗi nên phải tắt hẳn. Bỏ cả hai khoá phụ vì chúng vô nghĩa
    # khi retryOnFail tắt — giữ lại là mời người sau bật lại mà tưởng đã cân nhắc.
    for khoa in ("retryOnFail", "maxTries", "waitBetweenTries"):
        assert khoa not in n, f"{ten}: còn {khoa}={n[khoa]!r}"


@pytest.mark.parametrize("ten", HAI_NODE_BRAIN)
def test_node_brain_co_cong_loi(ten):
    wf = _wf()
    n = _node(wf, ten)
    assert n.get("onError") == "continueErrorOutput", f"{ten}: onError={n.get('onError')!r}"
    outs = wf["connections"][ten]["main"]
    assert len(outs) == 2, f"{ten}: cần đúng 2 cổng (0 = thành công, 1 = lỗi), có {len(outs)}"
    assert outs[1], f"{ten}: cổng lỗi không nối tới đâu — lỗi sẽ biến mất"


def test_cac_node_con_lai_nguyen_va_duong_thanh_cong_khong_doi():
    wf = _wf()
    ten = {n["name"] for n in wf["nodes"]}
    assert NODE_GOC <= ten, f"mất node: {NODE_GOC - ten}"
    # Mọi kết nối thành công vẫn ở cổng 0 và trỏ đúng node kế tiếp, và không có kết nối nào khác.
    for nguon, dich in DUONG_THANH_CONG:
        assert _lien_ket(wf, nguon, 0) == [dich], f"cổng 0 của {nguon!r} đã đổi"
    assert len(DUONG_THANH_CONG) == len(NODE_GOC) - 1
    # Hai node Brain vẫn gọi đúng URL với đúng thân yêu cầu (chỉ đổi cách xử lý lỗi).
    assert _node(wf, CHON_HANG)["parameters"]["url"] == "={{ $env.BRAIN_BASE_URL }}/tools/carrier-selection"
    assert _node(wf, CHON_HANG)["parameters"]["jsonBody"] == "={{ JSON.stringify($json.payloadSelection) }}"
    assert _node(wf, TINH_GIA)["parameters"]["url"] == "={{ $env.BRAIN_BASE_URL }}/tools/quote"
    assert _node(wf, TINH_GIA)["parameters"]["jsonBody"] == "={{ JSON.stringify($json.quotePayload) }}"


def test_nhanh_loi_bao_discord_roi_tra_loi_webhook_goc():
    wf = _wf()
    loi = _nhanh_loi(wf)
    kieu = {t: _node(wf, t)["type"] for t in loi}

    discord = [t for t in loi if kieu[t] == "n8n-nodes-base.httpRequest"
               and _node(wf, t)["parameters"].get("url") == DISCORD_URL]
    assert len(discord) == 1, f"nhánh lỗi phải có đúng một node báo Discord, thấy {discord}"

    # Webhook gốc LUÔN được trả lời sau khi báo — webhook đặt responseMode=responseNode, không trả
    # lời thì Brain đợi tới hết 30 giây rồi nói "lỗi kết nối n8n".
    sau_discord = _den_duoc(wf, _lien_ket(wf, discord[0], 0))
    respond = [t for t in sau_discord if kieu.get(t) == "n8n-nodes-base.respondToWebhook"]
    assert len(respond) == 1, f"sau node Discord phải có đúng một node trả lời webhook, thấy {respond}"
    assert not _lien_ket(wf, respond[0], 0), "node trả lỗi phải là điểm cuối"


def test_nhanh_loi_khong_cham_vao_duong_thanh_cong():
    """Báo giá lỗi mà chạm 'Trả kết quả cho Brain' / 'Lưu nháp' là bịa ra một draft_id."""
    loi = set(_nhanh_loi(_wf()))
    cham = loi & NODE_CHI_CHO_THANH_CONG
    assert not cham, f"nhánh lỗi đi vào đường thành công: {cham}"
    assert loi - NODE_GOC, "nhánh lỗi phải gồm node MỚI, không tái dùng node cũ"


def test_discord_loi_dung_cung_bien_voi_node_duyet():
    wf = _wf()
    duyet = _node(wf, "Báo chủ DN duyệt")["parameters"]["url"]
    assert duyet == DISCORD_URL
    node_loi = [t for t in _nhanh_loi(wf) if _node(wf, t)["parameters"].get("url") == DISCORD_URL]
    assert node_loi and _node(wf, node_loi[0])["parameters"]["url"] == duyet


def test_node_discord_loi_khong_nuot_loi_cua_chinh_no():
    """Discord cũng hỏng thì để execution ĐỎ (webhook trả 500): im lặng ở đây là quay về như cũ."""
    wf = _wf()
    for t in _nhanh_loi(wf):
        if _node(wf, t)["parameters"].get("url") == DISCORD_URL:
            assert _node(wf, t).get("onError", "stopWorkflow") == "stopWorkflow"


# ---------------------------------------------------------------------------
# Đoạn JS thật của node dựng cảnh báo (chạy trong Node)
# ---------------------------------------------------------------------------

_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const rows = r => ({ all: () => r.map(json => ({ json })), first: () => ({ json: r[0] }) });
const nodes = {};
for (const [k, v] of Object.entries(input.nodes || {}))
  nodes[k] = Array.isArray(v) ? rows(v) : { first: () => ({ json: v }), all: () => [{ json: v }] };
const $ = name => { if (!(name in nodes)) throw new Error('node không có trong harness: ' + name); return nodes[name]; };
$.input = rows(input.input || [{}]);
$.env = {};
const prevNode = 'prevNode' in input ? { name: input.prevNode } : undefined;
const execution = { id: input.executionId || '0' };
try {
  let ra;
  if (input.code !== undefined) {
    ra = new Function('$', '$input', '$env', '$prevNode', '$execution', input.code)($, $.input, $.env, prevNode, execution)[0].json;
  } else {
    ra = new Function('$', '$json', '$env', 'return (' + input.expr + ')')($, $.input.first().json, $.env);
  }
  console.log(JSON.stringify({ ok: ra === undefined ? null : ra }));
} catch (e) { console.log(JSON.stringify({ error: e.message })); }
"""


def _node_exe() -> str:
    exe = shutil.which("node")
    if exe is None:
        pytest.fail("cần Node để chạy đoạn JS thật của workflow n8n (test này không được skip)")
    return exe


def _chay(**phan: object) -> object:
    p = subprocess.run(
        [_node_exe(), "-e", _HARNESS], input=json.dumps(phan, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert "ok" in out, out
    return out["ok"]


def _node_dung_canh_bao(wf: dict) -> dict:
    ten = [t for t in _nhanh_loi(wf) if _node(wf, t)["type"] == "n8n-nodes-base.code"]
    assert len(ten) == 1, f"nhánh lỗi phải có đúng một node code dựng cảnh báo, thấy {ten}"
    return _node(wf, ten[0])


def _node_tren_nhanh(wf: dict, kieu: str) -> dict:
    ten = [t for t in _nhanh_loi(wf) if _node(wf, t)["type"] == kieu]
    assert len(ten) == 1, f"cần đúng một node {kieu} trên nhánh lỗi, thấy {ten}"
    return _node(wf, ten[0])


def _bieu_thuc(gia_tri: str) -> str:
    assert gia_tri.startswith("={{") and gia_tri.rstrip().endswith("}}"), gia_tri
    return gia_tri.strip()[3:-2].strip()


REQ = {"origin": "Hữu Nghị", "destination": "Bắc Ninh", "vehicle_type": "3T",
       "cargo_type": "Hàng khô", "customer_name": "Công ty A"}
LOI_GIA_DAU = "Giá dầu đã cũ 9 ngày — không dùng được để điều chỉnh giá"

# Bốn hình dạng `json.error` có thể gặp (n8n đổi theo phiên bản) + chuỗi trần + danh sách lỗi
# kiểm tra đầu vào của FastAPI. Mỗi hình dạng phải để lộ lời của Brain trong cảnh báo.
HINH_DANG_LOI = {
    "context.data là đối tượng": {"message": "Unprocessable", "httpCode": "422",
                                   "context": {"data": {"detail": LOI_GIA_DAU}}},
    "description": {"message": "The service was not able to process your request",
                    "httpCode": "422", "description": LOI_GIA_DAU},
    "cause.response.body": {"message": "Request failed", "cause": {"response": {
        "status": 422, "body": {"detail": LOI_GIA_DAU}}}},
    "thân là chuỗi JSON": {"httpCode": "422", "context": {"data": json.dumps({"detail": LOI_GIA_DAU},
                                                                             ensure_ascii=False)}},
    "chuỗi trần": LOI_GIA_DAU,
}


def _canh_bao(error: object, prev: str = TINH_GIA, req: dict | None = None) -> dict:
    wf = _wf()
    return _chay(
        code=_node_dung_canh_bao(wf)["parameters"]["jsCode"],
        nodes={"Ghép dữ liệu": {"req": req or REQ}},
        input=[{"error": error}], prevNode=prev, executionId="777",
    )


def _mo_ta(ra: dict) -> str:
    return json.loads(ra["discord_body"])["embeds"][0]["description"]


@pytest.mark.parametrize("hinh", list(HINH_DANG_LOI))
def test_canh_bao_chep_loi_cua_brain_va_neu_tuyen_loai_xe(hinh):
    ra = _canh_bao(HINH_DANG_LOI[hinh])
    mo_ta = _mo_ta(ra)
    assert LOI_GIA_DAU in mo_ta, f"không thấy lời của Brain: {mo_ta}"
    assert "Hữu Nghị → Bắc Ninh" in mo_ta and "3T" in mo_ta
    assert "Công ty A" in mo_ta, "chủ DN cần biết khách nào đang đợi"
    assert "tính báo giá" in mo_ta, "phải nói lỗi ở bước nào"
    assert "777" in mo_ta, "kèm mã execution để chủ DN/quản trị tìm lại trong n8n"


def test_canh_bao_phan_biet_hai_buoc_theo_node_gui_toi():
    assert "chọn hãng xe" in _mo_ta(_canh_bao(LOI_GIA_DAU, prev=CHON_HANG))
    assert "tính báo giá" in _mo_ta(_canh_bao(LOI_GIA_DAU, prev=TINH_GIA))


def test_canh_bao_danh_sach_loi_kiem_tra_dau_vao_cua_fastapi():
    loi = {"httpCode": "422", "context": {"data": {"detail": [
        {"loc": ["body", "current_fuel_price"], "msg": "Input should be greater than 0"}]}}}
    mo_ta = _mo_ta(_canh_bao(loi))
    assert "current_fuel_price" in mo_ta and "greater than 0" in mo_ta


def test_canh_bao_khong_co_chi_tiet_van_dung_duoc():
    """Không biết lỗi là gì thì NÓI không biết — không sập, không bịa lý do."""
    for rong in ({}, None, "", {"message": ""}):
        ra = _canh_bao(rong)
        mo_ta = _mo_ta(ra)
        assert "không có chi tiết" in mo_ta
        assert ra["phan_hoi"]["ok"] is False


def test_canh_bao_khong_sap_khi_loi_tham_chieu_vong():
    code = _node_dung_canh_bao(_wf())["parameters"]["jsCode"]
    # JSON không biểu diễn được vòng, nên dựng ngay trong Node thay vì truyền qua stdin.
    ket_qua = subprocess.run(
        [_node_exe(), "-e", r"""
const code = JSON.parse(require('fs').readFileSync(0, 'utf8')).code;
const e = { message: 'vong', httpCode: '502' }; e.cause = e; e.context = { data: e };
const $ = () => ({ first: () => ({ json: { req: { origin: 'A', destination: 'B', vehicle_type: '3T' } } }) });
const ra = new Function('$', '$input', '$env', '$prevNode', '$execution', code)(
  $, { first: () => ({ json: { error: e } }) }, {}, { name: 'Tính báo giá (Brain)' }, { id: '1' })[0].json;
console.log(JSON.stringify({ ok: ra.phan_hoi.ok, hasBody: typeof ra.discord_body }));
"""],
        input=json.dumps({"code": code}), capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert ket_qua.returncode == 0, ket_qua.stderr
    assert json.loads(ket_qua.stdout) == {"ok": False, "hasBody": "string"}


def test_canh_bao_cat_loi_qua_dai_de_vua_gioi_han_discord():
    mo_ta = _mo_ta(_canh_bao({"context": {"data": {"detail": "x" * 20000}}}))
    assert len(mo_ta) < 4000, "Discord từ chối embed.description > 4096 ký tự — mất luôn cảnh báo"


def test_canh_bao_khong_de_loi_pha_vo_khoi_ma_cua_discord():
    mo_ta = _mo_ta(_canh_bao("lỗi có ``` dấu rào mã ``` bên trong"))
    assert mo_ta.count("```") == 2, "thân lỗi chứa ``` làm vỡ khối mã của Discord"


def test_node_loi_khong_chua_nguong_gia_dau_r4():
    """R4: ngưỡng giá dầu thuộc Brain. Node lỗi chỉ chép — không so số ngày, không phân loại."""
    code = _node_dung_canh_bao(_wf())["parameters"]["jsCode"]
    for dau_hieu in ("fuel", "giá dầu", "FUEL_PRICE", "days", "ngày >=", ">= 7", "> 7"):
        assert dau_hieu not in code, f"node lỗi chứa logic/ngưỡng ({dau_hieu!r}) — thuộc về Brain"


def test_phan_hoi_webhook_khong_co_draft_id_va_noi_ro_loi():
    wf = _wf()
    code_node = _node_dung_canh_bao(wf)
    ra = _canh_bao(HINH_DANG_LOI["description"])
    respond = _node_tren_nhanh(wf, "n8n-nodes-base.respondToWebhook")
    thuc_te = _chay(expr=_bieu_thuc(respond["parameters"]["responseBody"]),
                    nodes={code_node["name"]: ra})
    phan_hoi = json.loads(thuc_te)
    assert phan_hoi["ok"] is False and phan_hoi["status"] == "error"
    assert "draft_id" not in phan_hoi, "lỗi mà có draft_id là tuyên bố đã tạo nháp"
    assert LOI_GIA_DAU in phan_hoi["error"] and phan_hoi["stage"] == "tính báo giá"


def test_thong_diep_discord_la_json_hop_le_cho_node_http():
    wf = _wf()
    code_node = _node_dung_canh_bao(wf)
    ra = _canh_bao(HINH_DANG_LOI["description"])
    discord = _node_tren_nhanh(wf, "n8n-nodes-base.httpRequest")
    thuc_te = _chay(expr=_bieu_thuc(discord["parameters"]["jsonBody"]), nodes={code_node["name"]: ra})
    assert json.loads(thuc_te)["embeds"][0]["title"].startswith("❌")


# ---------------------------------------------------------------------------
# Hợp đồng với chat.py: phản hồi lỗi của n8n -> câu "chưa xác nhận", không phải "Đã tạo nháp"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_py_noi_chua_xac_nhan_khi_n8n_tra_phan_hoi_loi(monkeypatch):
    from src.api import dependencies
    from src.api.routes import chat as chat_mod
    from src.core import utils as utils_mod

    wf = _wf()
    code_node = _node_dung_canh_bao(wf)
    respond = _node_tren_nhanh(wf, "n8n-nodes-base.respondToWebhook")
    # Chính chuỗi mà node "Trả lỗi cho Brain" sẽ gửi qua mạng.
    than = json.loads(_chay(expr=_bieu_thuc(respond["parameters"]["responseBody"]),
                            nodes={code_node["name"]: _canh_bao(HINH_DANG_LOI["description"])}))

    async def fake_extract(msg, history=None):
        return json.dumps({
            "origin": "Hữu Nghị", "destination": "Bắc Ninh", "vehicle_type": "3T",
            "cargo_type": "Hàng khô", "pickup_date": "2026-11-20",
            "customer_name": "Công ty A", "customer_email": "a@example.test",
        })

    class FakeManager:
        extract_quote_request = staticmethod(fake_extract)

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return than

    class FakeClient:
        async def post(self, url, json=None, timeout=None):
            return FakeResp()

    monkeypatch.setattr(dependencies.runtime, "manager", FakeManager())
    monkeypatch.setenv("N8N_QUOTE_WEBHOOK_URL", "http://n8n.local/webhook/logistics-quote")
    monkeypatch.setattr(utils_mod.HttpClientPool, "get_client", staticmethod(lambda: FakeClient()))

    out = await chat_mod._handle_logistics_quote("báo giá...", "req-test")

    assert "chưa xác nhận" in out
    assert "Đã tạo nháp" not in out
