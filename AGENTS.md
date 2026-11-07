# AGENTS.md — Chỉ thị vận hành cho Agent kỹ thuật, dự án ANSER Brain

> **Phiên bản:** 2.0 — 27/07/2026
> **Đọc kèm:** [ARCHITECTURE.md](ARCHITECTURE.md) là nguồn sự thật về *kiến trúc*. File này là nguồn sự thật về *cách làm việc*.
> **Thay thế:** AGENTS.md v1.0 (giả định A100 80GB + Qwen2.5-Coder-32B — cả hai đều không còn đúng).

---

## 1. Phạm vi & ranh giới

| Repo | Vai trò | Quyền của agent |
|---|---|---|
| **`AI_ANSER` (Brain)** | FastAPI service cung cấp năng lực AI | ✅ Toàn quyền sửa |
| **`ANSER Body`** (Flask, VPS, Neon, n8n) | Nền tảng nghiệp vụ, gọi Brain qua HTTP | ❌ **KHÔNG ĐƯỢC SỬA.** Chỉ được *đề xuất* thay đổi bằng văn bản |

Khi một việc cần Body đổi (ví dụ thêm bảng logistics ở [ARCHITECTURE.md §10](ARCHITECTURE.md)), agent viết bản đặc tả thay đổi và **dừng lại chờ người quyết định** — không tự ý mock hay giả định Body đã có.

**Pull Request TÍNH LÀ đề xuất** (chủ dự án chốt 04/11/2026). Mở PR vào repo Body là hợp lệ, và với thay đổi nhỏ thì tốt hơn issue: issue là *nhờ họ làm việc*, PR là *nhờ họ đọc việc đã làm*. Quyền quyết vẫn ở họ — merge hoặc đóng.

Ranh giới cụ thể, vì agent có quyền `admin` trên repo Body qua org:

| ✅ Được | ❌ Không |
|---|---|
| Mở nhánh mới trên repo Body | Đẩy thẳng vào `master` |
| Mở PR, mở issue, bình luận | **Tự merge PR của chính mình** |
| Gắn sub-issue xuyên repo | Đổi cấu hình repo, xoá nhánh người khác |

**Có quyền không có nghĩa là được phép.** Quyền admin đến từ việc tài khoản là owner của org, không phải từ việc ranh giới này được nới ra.

Quy trình và bản nháp: [`docs/de-xuat-body/`](docs/de-xuat-body/).

**Viết cho Body thì giả định họ không biết gì về Brain.** Hai đội, hai repo, hai bộ nghiệp vụ. Người bên Body không biết `R1` là gì, `BR-01` là sự cố nào, `reporting.py` làm gì. Mỗi PR hoặc issue gửi sang phải **tự đứng được** — không bắt ai mở repo Brain ra tra. Thuật ngữ riêng thì giải thích ngay tại chỗ, một câu.

Luật đầy đủ, áp cho **mọi** tài liệu trong đội lẫn ngoài đội: [`docs/VIET-CHO-AI-DOC.md`](docs/VIET-CHO-AI-DOC.md).

### Bản sao mô tả

[`agent_middleware.py`](src/core/agent_middleware.py) và các khối `SCHEMA MAP` trong [`memory.py`](src/core/memory.py), [`saas_api.py`](src/core/saas_api.py) là **bản sao mô tả** của thứ thuộc về Body. Chúng lệch được, và đã từng lệch. Trước khi tin vào chúng, đối chiếu lại với Body.

**Đối chiếu bằng lệnh, đừng nhớ:**

```bash
python offline_training/doi_chieu_hop_dong_body.py
```

Nó tải `brain.ts` của Body về và so từng trường với các schema đầu vào trong [`tools.py`](src/api/routes/tools.py), mã thoát 1 nếu Body gửi trường Brain không nhận. Chạy nó **trước khi gộp vào `main`**.

Từ 04/11/2026 `_ToolIn` đặt `extra="forbid"`, nên mỗi chỗ lệch không còn bị bỏ im lặng nữa mà thành một lời gọi hỏng — đó là điều cần thiết (BR-01: một phụ phí bị bỏ im lặng làm sai báo giá gửi khách), nhưng nó cũng có nghĩa là việc đối chiếu không được phép là chuyện nhớ thì làm.

> **Repo Body đổi chỗ hai lần trong một tuần** (`Dgsonn/ANSER-v2` → `Dgsonn/ANSER-logistics` → `ANSER-Logistics/ANSER-logistics-body`). URL nằm ở hằng số `URL_BRAIN_TS` trong chính script. Script báo lỗi tải thì kiểm URL trước khi kết luận là mạng hỏng.

---

## 2. Năm ràng buộc bất biến

Đây là phiên bản hành động của 5 nguyên tắc trong [ARCHITECTURE.md §1](ARCHITECTURE.md). Vi phạm bất kỳ điều nào ⇒ code bị từ chối, không tranh luận.

### R1 — Deterministic-first

**LLM không bao giờ tính toán.**

| ❌ Cấm | ✅ Bắt buộc |
|---|---|
| Prompt kiểu "tính giúp tôi tổng tiền thuế" | `MCPServer.calculate_vat()` — code thuần |
| Cho LLM tự cộng dòng hóa đơn | `validate_invoice_total()` tính lại toàn bộ |
| Cho LLM suy ra "vì sao lệch 3 triệu" | `reconciliation.py` phân rã kèm bằng chứng, LLM chỉ diễn giải |
| Cho LLM sinh SQL tự do rồi chạy | Tool có tham số ràng buộc, SQL viết sẵn |
| Cho LLM tự cộng doanh thu/chi phí ra lợi nhuận | `reporting.build_report()` — code thuần, LLM chỉ diễn giải |
| Trong vòng agentic: model tự tính rồi tuyên bố kết quả | Grammar `oneOf` gọi-tool/trả-lời; mọi con số phải đến từ kết quả tool |

Kiểm tra nhanh trước khi commit: *nếu model đọc sai một chữ số, có bản ghi sổ sách nào sai theo không?* Nếu có — thiếu lớp tất định.

**Thiếu dữ liệu thì nói thiếu, không điền 0.** `reporting.py` không coi giá vốn trống là 0 (làm thế thì lãi gộp = doanh thu — một con số sai mà trông rất đẹp); nó tính `cogs_coverage_pct`, hạ `confidence` và cảnh báo. Con số tài chính sai mà *nghe có vẻ đúng* là loại lỗi tệ nhất: không ai phát hiện tới lúc quyết toán.

**Nhưng "nói thiếu" có hai cách, và chọn sai cách là tạo ra đúng cái lỗi đang tránh.** Hai ví dụ trong repo này cố ý làm ngược nhau — đừng "sửa" cho giống nhau:

| Hàm | Nhánh thiếu dữ liệu | Vì sao |
|---|---|---|
| [`reporting.build_report`](src/core/reporting.py) | **Trả đủ khoá**, `cogs_coverage_pct: None`, `confidence: "không có dữ liệu"` | Body khai bốn trường này là bắt buộc và render chúng. Bỏ khoá đi thì `?? 0` bên Body hiện **0%** — một con số trông như kết quả đo. Có khoá kèm nhãn trung thực thì màn hình nói thật. |
| [`mcp_server.validate_invoice_total`](src/core/mcp_server.py) | **Bỏ hẳn khoá** `calculated_total` / `difference`, chỉ giữ `is_valid: False` + `error` | Không tính lại được thì **không có con số nào** để ai đó lỡ tay đem đi dùng. Trả `calculated_total: None` là mời gọi một `?? 0` ở đâu đó rồi đẻ ra "hoá đơn lệch X đồng" — đúng thảm hoạ BR-01. |

Quy tắc phân biệt: **khoá có mặt thì người đọc sẽ hiển thị nó.** Nếu người đọc *đòi* khoá đó (hợp đồng khai bắt buộc) thì trả khoá kèm giá trị tự nói ra mình là "chưa biết". Nếu khoá đó chỉ tồn tại để chứa một phép tính **đã không chạy** thì đừng tạo ra nó.

Soát máy móc các chỗ một hàm trả về hai hình dạng khác nhau: `python offline_training/soat_hinh_dang_tra_ve.py`. Nó tìm *hình dạng*, không tìm *lỗi* — mỗi kết quả phải tự trả lời câu hỏi ở bảng trên.

### R2 — Chủ quyền dữ liệu

**Không gửi dữ liệu khách hàng tới bất kỳ LLM bên thứ ba nào.** Không OpenAI, không Gemini, không Claude, không DeepSeek — kể cả "chỉ để test".

Dữ liệu khách hàng gồm: tồn kho, doanh thu, công nợ, **bảng giá cước**, **tỷ lệ biên lợi nhuận**, danh sách khách, nội dung hóa đơn, lịch sử chat.

Ngoại lệ duy nhất — nguồn công khai, **chỉ đọc, không kèm tham số chứa dữ liệu khách**: giá xăng dầu, thời tiết, tỷ giá, tìm kiếm web.

> ⚠️ [`evaluate_system.py`](src/evaluate_system.py) **đã chặn chạy** (04/11/2026) — nó đã bị [`benchmark_v3.py`](offline_training/benchmark_v3.py) thay thế. Ngoài rủi ro R2 (gửi prompt + ground truth + đầu ra model tới DeepSeek, không rào nào chặn việc lỡ chạy trên dữ liệu khách), judge của nó chấm theo **định dạng Make.com** — thứ R4 đã bỏ — nên mọi điểm số nó đưa ra đều đo sai thứ. `benchmark_v3` chấm n8n bằng chính `validate_workflow()` của runtime và chấm narration bằng `src/core/grounding.py`, tức phép kiểm lúc đo và lúc chạy là MỘT. Lý do đầy đủ ở docstring đầu file.

> ⚠️ `requirements.txt` có `openai`. Nếu package này được dùng để gọi API ngoài với dữ liệu khách — đó là vi phạm R2. Dùng nó làm client cho vLLM OpenAI-compatible server **nội bộ** thì hợp lệ.

**R2b — Kỷ luật bí mật (bổ sung 27/07/2026, sau sự cố lộ mật khẩu Neon):**

1. **Không bao giờ hardcode credential** — kể cả trong script một lần (`src/archive/`), kể cả trong `_backups/`. Sự cố thật: 3 script archive chứa nguyên chuỗi Neon Postgres, nhân bản thành 12 file qua các bản backup, bị đẩy lên GitHub public → Neon phát cảnh báo, phải xoay mật khẩu.
2. **Trước khi push lịch sử lên một remote MỚI hoặc public**: bắt buộc quét bí mật trên TOÀN BỘ lịch sử (`git log --all -S` với các mẫu `postgres://.*:.*@`, `npg_`, `sk-`, `hf_`, `AIza`...), không chỉ quét HEAD. Push lịch sử = publish mọi commit từng tồn tại.
3. **Đưa bất kỳ giá trị bảo mật nào vào env / đổi cách quản lý bí mật → HỎI Ý KIẾN chủ dự án TRƯỚC** — chỉ thị trực tiếp của chủ dự án. Tái sử dụng biến đã có (như `DATABASE_URL`) để sửa sự cố thì được, nhưng phải báo lại rõ ràng.
4. Credential đã lộ là credential **đã chết** — xoá khỏi git không thu hồi được nó (bot quét GitHub trong vài giây). Việc đầu tiên luôn là **xoay/vô hiệu credential**, dọn repo chỉ là bước sau.

**Lưu ý trung thực với khách:** ở bậc hạ tầng T0/T1 (GPU thuê), R2 mới thỏa mãn *một phần* — xem [ARCHITECTURE.md §4.3](ARCHITECTURE.md). Không quảng cáo "dữ liệu không rời hệ thống" trước khi đạt T3 (máy tự sở hữu).

### R3 — Kỷ luật ngân sách

Trần hạ tầng phục vụ pilot miễn phí: **5.000.000đ/tháng. Thấp hơn càng tốt.** Mục tiêu hiện tại là bậc T0 ≈ 750.000đ/tháng.

Mọi PR làm tăng chi phí vận hành (model to hơn, context dài hơn, thêm GPU, thêm service thường trực) phải kèm:
1. Chi phí tăng thêm, tính bằng VNĐ/tháng
2. Chỉ số nghiệp vụ nào cải thiện, đo bằng cách nào
3. Doanh thu nào chi trả cho phần tăng đó

Không có 3 mục này ⇒ PR bị từ chối.

### R4 — Một định dạng, một nguồn sự thật

**Định dạng workflow duy nhất: n8n.** Make.com và engine nội bộ Body không phải đích sinh code.

**Nguồn duy nhất: [`workflow_schema.py`](src/core/workflow_schema.py).** Cả ba chân — prompt dạy model, lớp kiểm đầu ra, và grammar `guided_json` — đều **dựng từ cùng một `catalog`** trong file đó.

| Nơi | Thực tế trong mã nguồn hôm nay |
|---|---|
| [`prompts.py::CODER_SYSTEM`](src/core/prompts.py) | Chỉ có chỗ giữ chỗ `{tools}` / `{example}`. Không chứa tên node nào. |
| [`agent_middleware.py`](src/core/agent_middleware.py) | Lớp mỏng, 6 hàm, mỗi hàm một dòng `return workflow_schema.…`. Không giữ trạng thái. |
| [`chat.py`](src/api/routes/chat.py) | `_validate_workflow = validate_workflow` — một dòng gán bí danh. |

Bản trước của mục này ghi *"Ba nơi sau phải luôn khớp nhau. Sửa một nơi mà không sửa hai nơi kia là lỗi"*. **Chỉ dẫn đó sai hướng** (sửa 04/11/2026) — nó bảo người đọc *bảo trì ba bản sao*, đúng thứ R4 cấm. Đoạn lược đồ DB ngay dưới đây đã tự nhận ra điều đó cho trường hợp của nó ("Đồng bộ ba bản chép tay là giữ nguyên thứ R4 cấm, chỉ gọn hơn") nhưng bảng n8n thì chưa ai soát lại. Mã nguồn đã hợp nhất xong từ 27/07/2026 — chỉ tài liệu còn kẹt lại ở cấu trúc cũ.

**Đối chiếu bằng lệnh, đừng nhớ.** Đo 04/11/2026: 10 node type, cả bốn chỗ (catalog, prompt, `allowed_types()`, grammar) khớp tuyệt đối; `BLOCKED_NODE_TYPES` rời khỏi catalog.

```bash
pytest tests/test_agent_middleware.py tests/test_deterministic_core.py -q
```

Lệch pha còn có thể xảy ra ở quy mô nhỏ hơn ba file: `render_node_catalog()` viết ra thứ **model được dạy**, `validate_workflow()` kiểm thứ **model phải làm**. Hai hàm cùng file, cùng đọc một dict, nhưng là hai vòng lặp riêng — thêm một điều kiện lọc ở một bên là dạy model một định dạng mà bên kia từ chối. Ba test chặn đúng chỗ đó: tập node khớp, `typeVersion` khớp, và node bị chặn không lọt vào prompt.

**Lược đồ DB: Brain KHÔNG giữ bản sao nào.** Body gửi lược đồ kèm ngữ cảnh người dùng; [`agent_middleware.get_db_schema()`](src/core/agent_middleware.py) trả về một placeholder, đúng như vậy, "để tránh định nghĩa lược đồ ở nơi thứ hai".

Bản trước của mục này bảo đồng bộ ba nơi — `prompts.py::DB_SCHEMA`, `offline_training/db_schema.txt`, SQL trong [`saas_api.py`](src/core/saas_api.py) — và nêu lệch `sales.amount` vs `sales.total_amount`. **Chỉ dẫn đó sai hướng, và tranh luận đó đã vô nghĩa** (sửa 04/11/2026):

- `Prompts.DB_SCHEMA` đã xoá. Nó không với tới được từ bất kỳ đường nào, và mô tả 10 bảng mà chỉ 3 còn tồn tại bên Body. Bảng `sales` không có — Body dùng `sales_invoices` / `sales_invoice_items` / `invoice_payments`. Lý do đầy đủ nằm ngay chỗ đã xoá trong [`prompts.py`](src/core/prompts.py).
- Đồng bộ ba bản chép tay là giữ nguyên thứ R4 cấm, chỉ gọn hơn. Một nguồn nghĩa là **một**, và nguồn đó ở Body.
- `offline_training/db_schema.txt` **đã xoá** (04/11/2026). Không file `.py` nào import nó, và nội dung đã lệch khỏi Body. Lấy lại bằng `git show f77096c:offline_training/db_schema.txt`.
- `SCHEMA MAP` trong `saas_api.py` **đã sửa** theo lược đồ thật của Body (04/11/2026): 5 trong 10 định danh sai, trong đó `workspace_id` ánh xạ tới một khái niệm Body không có. Lý do đầy đủ nằm trong chính khối đó.
- Còn một bản sao nữa chưa xử: khối `[LƯỢC ĐỒ]` trong `Prompts.INVOICE_SYSTEM`. **Bản trước của dòng này ghi "Prompt đó đang chạy" — SAI** (sửa 04/11/2026). Đo bằng cách tìm `INVOICE_SYSTEM` trong `src/`, `tests/`, `offline_training/`: **không một tham chiếu nào** ngoài chính dòng khai báo. 11 trong 12 hằng số của `Prompts` có người dùng; đây là cái duy nhất bằng 0. Nên xoá khối đó **không có rủi ro chạy nào** — cái chặn chỉ còn là câu hỏi S5 nên biểu diễn nhánh hoá đơn thế nào. Chỉ dẫn đầy đủ nằm ngay cạnh nó trong [`prompts.py`](src/core/prompts.py).

### R5 — Hardware-neutral

**Không hardcode giả định phần cứng.** Không tên GPU, không con số VRAM, không đường dẫn `/content/drive/...` trong code.

Mọi tham số phần cứng đọc từ biến môi trường, có mặc định an toàn. **Tên dưới đây là tên THẬT trong code** — đã đối chiếu 04/11/2026:

```python
TEXT_MODEL_ID          # đường dẫn hoặc HF id. KHÔNG có mặc định, cố ý
VISION_MODEL_ID        # Qwen/Qwen2.5-VL-3B-Instruct
VLLM_BASE_URL          # http://127.0.0.1:8001/v1
TEXT_GPU_FRACTION      # 0.55 (compose: 0.62, vì vision là container riêng)
TEXT_MAX_MODEL_LEN     # 32768
TEXT_QUANTIZATION      # rỗng = để vLLM tự nhận từ config.json của model
ENV                    # LOCAL | GPU | COLAB | SERVER
VLLM_MODEL             # khớp --served-model-name của vLLM server
```

Bản trước của danh sách này ghi `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `QUANTIZATION`. **Ba tên đó không tồn tại trong code** — đo 04/11/2026: `grep getenv` trên `src/` cho 0 lần cho cả ba. Ai đọc AGENTS rồi đặt `GPU_MEMORY_UTILIZATION` trong `.env` sẽ thấy không có gì xảy ra, và tin rằng mình đã cấu hình xong. Một cái tên sai trong tài liệu cấu hình tệ hơn không ghi gì: không ghi thì người ta đi đọc code.

`TEXT_GPU_FRACTION` cũng **chưa từng được code đọc** cho tới 04/11/2026 — `config.py` hardcode `0.55`, con số đo trên L4 22,5GB. Đường server đọc được từ env từ trước (compose truyền `--gpu-memory-utilization`), chỉ đường trong-tiến-trình còn kẹt. Nên tiêu chí nghiệm thu bên dưới **đang không đạt** ở đúng đường đó: chuyển sang 3090 24GB thì phải sửa code. Đã nối vào env, mặc định giữ `0.55` nên hành vi không đổi.

Cặp `ENV` + `VLLM_BASE_URL` chọn backend ở đúng một chỗ, `engine.py::chon_backend()`. Có `VLLM_BASE_URL` thì text đi vLLM server ở mọi `ENV`. `SERVER` nghĩa là Brain không nạp model nào: bắt buộc có `VLLM_BASE_URL`, vision tắt có tuyên bố. Giá trị `ENV` lạ là lỗi cấu hình, không lặng lẽ nạp CUDA. Bảng đầy đủ ở [SO_TAY_NGUOI_MOI.md §2.4](SO_TAY_NGUOI_MOI.md).

Tiêu chí nghiệm thu: **chuyển từ GPU thuê sang máy tự sở hữu chỉ đổi `.env`, không sửa dòng code nào.**

---

## 3. Môi trường

### 3.1. Ba môi trường

| Môi trường | Phần cứng | `ENV` | Hành vi |
|---|---|---|---|
| **Dev cục bộ** | Windows 11, GTX 1660 Ti 6GB | `LOCAL` | Mock response, **không nạp model thật**. Toàn bộ logic tất định + routing + API vẫn chạy và test được |
| **GPU thuê** (hiện tại) | RTX 3090 24GB, Linux | `GPU` | vLLM server riêng + vision. Đích triển khai bậc T0/T1 |
| **Máy tự sở hữu** (tương lai) | RTX 3090/4090 24GB | `GPU` | Cùng code, chỉ khác `.env` |

Chế độ `LOCAL` không phải "chế độ giả vờ" — nó là thứ cho phép test toàn bộ tầng tất định (nơi P1 nói rằng phần lớn giá trị nằm ở đó) mà không cần GPU. Giữ nó hoạt động.

> ❌ **Colab không còn là môi trường production.** Điều khoản Colab Paid cấm phục vụ web service. Chỉ dùng Colab cho fine-tune / quantize / thử nghiệm rời rạc — xem [ARCHITECTURE.md §4.4](ARCHITECTURE.md).

### 3.1b. Kiểm thử GPU chạy trên Google Colab

Chốt 27/07/2026: test có GPU thật chạy trên **Colab** (không phải máy dev). Người làm Brain được tạo script hoặc notebook đo khi việc cần, ví dụ `offline_training/do_ngan_sach_ctx.py` cho BR-04. (Bản trước ghi "chỉ soạn khi chủ dự án yêu cầu, không tự tạo sớm" — câu đó sai, đã sửa 26/10/2026.) (Colab chỉ cho thử nghiệm rời rạc — production vẫn bị cấm theo §3.1.)

### 3.1c. Dữ liệu giá phải sát thời gian thực

Yêu cầu nghiệp vụ trực tiếp từ chủ dự án: *"hôm nay 25 nghìn, ngày mai 30 nghìn"* — báo giá dựa trên giá cũ là báo giá sai. Hệ quả thiết kế:

1. Tool nào nhận tham số giá (`current_fuel_price`...) thì **caller phải lấy giá mới nhất tại thời điểm gọi**, không đọc giá trị cache cũ từ hôm trước.
2. Nguồn giá công khai (dầu, tỷ giá) cập nhật bằng n8n scheduled job — được phép gọi ra ngoài vì là dữ liệu công khai một chiều (R2).
3. Kết quả báo giá phải ghi kèm **thời điểm và giá đầu vào** đã dùng (đã có trong `internal` của `/tools/quote`) — để khi giá đổi, biết báo giá cũ dựa trên gì.

### 3.2. Cross-platform

1. **Đường dẫn:** dùng `pathlib`. Không hardcode `/` hay `\`. Code phải chạy cả Windows lẫn Linux.
2. **Không phụ thuộc lệnh bash** trong `subprocess`.
3. **Không hardcode credential.** Mọi bí mật qua `os.getenv()`.
4. **Ghim version** khi thêm thư viện vào `requirements.txt`.

---

## 4. Quy tắc code

### 4.1. Bắt buộc

| # | Quy tắc |
|---|---|
| 1 | **Constrained decoding thay cho retry.** Đầu ra JSON dùng `guided_json`. Đừng "hy vọng model làm đúng rồi retry" |
| 2 | **Không chặn event loop.** Inference nặng qua `run_in_executor` hoặc HTTP tới vLLM server |
| 3 | **Log có cấu trúc, không `print`.** `logger` + `extra={"request_id": ...}` |
| 4 | **Không nuốt exception.** `except Exception: pass` bị cấm. Ít nhất phải `logger.warning` kèm ngữ cảnh |
| 5 | **Tool tự validate đầu vào.** Không tin tham số model điền |
| 6 | **Tool ghi dữ liệu tạo `pending_review`.** Không tự động duyệt bất cứ thứ gì chạm tiền hoặc sổ sách |
| 7 | **Prompt chỉ sống trong [`prompts.py`](src/core/prompts.py).** Không rải chuỗi prompt khắp agent |
| 8 | **Sanitize đầu ra VLM.** Hóa đơn là dữ liệu ngoài — chống prompt injection trước khi đưa xuống Body |

### 4.2. Chống mục ruỗng

- Xoá code chết thay vì để lại. `RetailChatResponse`/`ProductExtraction` từng bị đánh dấu dead code — kiểm tra trước khi thêm schema mới.
- `src/archive/` **đã xoá** (05/08/2026): 15 script thời ProjectA_Backup/Make.com, trỏ vào đường dẫn Drive không còn tồn tại, không nơi nào import, và chiếm 215/252 lỗi lint của cả repo. Lấy lại bằng `git show 306a16c:src/archive/<file>` nếu cần đối chiếu.
- Sửa code là sửa tài liệu **trong cùng PR**. ARCHITECTURE.md v1.0 lệch khỏi code nhiều tháng và đã dẫn tới quyết định sai (chọn model theo A100 trong khi code chạy L4).

---

## 5. Quy trình làm việc

### 5.1. Trước khi viết code

1. **Đọc code, không đọc tài liệu cũ.** Tài liệu từng sai ở nhiều điểm quan trọng. Xác minh bằng file thật.
2. **Đối chiếu 5 ràng buộc.** Đề xuất vi phạm R1-R5 ⇒ dừng, không "làm tạm rồi sửa sau".
3. **Nêu chỉ số sẽ cải thiện** và cách đo. Không đo được ⇒ không biết có tác dụng hay không.

### 5.2. Giao thức phản biện

Không code nào được viết mà không có phản biện.

1. `@engineer` đề xuất giải pháp.
2. `@qa` **tìm cách phá nó** — trường hợp biên, lỗi đồng thời, dữ liệu bẩn, thư viện bịa.
3. Tinh chỉnh cho tới khi `@qa` xác nhận `STATUS: VERIFIED AND SAFE FOR EXECUTION`.
4. `@mentor` audit từng dòng, đặc biệt về R1 (LLM có lén tính toán không) và R2 (có dữ liệu nào rò ra ngoài không). Đóng dấu `[PASSED BY MENTOR]`.

Trọng tâm phản biện — 4 câu hỏi hỏi mọi lần:

- Nếu model trả về rác, có bản ghi sổ sách nào sai theo không? *(R1)*
- Payload này có chứa dữ liệu khách hàng, và nó đi tới đâu? *(R2)*
- Việc này làm tăng chi phí GPU bao nhiêu VNĐ/tháng? *(R3)*
- Định nghĩa này đã tồn tại ở chỗ khác chưa? *(R4)*

### 5.3. Kiểm thử

- Logic tất định (pricing, VAT, reconciliation) phải có unit test — đây là phần **không được phép sai**.
- Tầng API test bằng `ENV=LOCAL`, không cần GPU.
- Đổi định dạng workflow ⇒ cập nhật `tests/` trong cùng PR.
- Trước khi tuyên bố "xong": chạy `pytest`, dán kết quả. Test fail thì nói rõ là fail — không mô tả vòng vo.

---

## 6. Version control & sao lưu

### 6.0. `main` LÀ PRODUCTION (chủ dự án chốt 07/11/2026)

**`main` không phải nơi tích hợp. Nó là bản đang phục vụ.**

Nguyên văn chỉ thị: *"main thì phải test nhánh tính năng rất nhiều và chỉn chu, sau khi xác nhận nó hoàn toàn ổn định và hoạt động tốt mới đẩy lên main"*.

Hệ quả, và chúng đi ngược thói quen gộp sớm:

| | |
|---|---|
| Nhánh tính năng | nơi làm việc, gộp vào nhau thoải mái, CI xanh là đủ |
| `main` | chỉ nhận thứ **đã xác nhận ổn định**, không phải thứ **vừa xanh CI** |

`pytest` xanh **không phải** là tiêu chí để đẩy lên `main`. Nó là tiêu chí tối thiểu để không làm hỏng nhánh tính năng. Tiêu chí cho `main` là bảy mục ở §7 cộng với một lần chạy thật.

**Agent KHÔNG tự gộp vào `main`.** Mở PR thì được — đó là đề xuất. Quyết thời điểm gộp là của chủ dự án, vì chỉ người đó biết khi nào "đã xác nhận ổn định".

> **Hệ quả đã đo 07/11/2026:** `main` đang sau nhánh tính năng rất nhiều, và **CI của `main` đỏ** vì thiếu `python-multipart` + `openpyxl` trong bước cài. Không ai thấy suốt thời gian đó, vì mọi lượt "CI xanh" đều là CI của nhánh tính năng. Giữ `main` làm production thì phải chấp nhận nó tụt lại — nhưng **cổng chất lượng của nó vẫn phải chạy được**, nếu không thì lúc cần gộp sẽ không có gì nói cho biết `main` đang ở trạng thái nào. Xem `brain#91`.

### 6.1. Nhịp commit và sao lưu

1. **Quy tắc 5 thay đổi:** đúng khi chạm 5 file bị sửa, HOẶC trước bất kỳ thay đổi cấu trúc rủi ro cao nào ⇒ commit cục bộ.
2. **Cuối giai đoạn:** sau khi có `[PASSED BY MENTOR]` và người phê duyệt:
   - Sao lưu cục bộ có dấu thời gian vào `_backups/Phase_X_YYYYMMDD/` (bỏ `__pycache__`, `.venv`)
   - `git add . && git commit && git push`
3. **Nếu sandbox chặn:** sinh script Python cross-platform `execute_backup_and_push.py` để người dùng chạy một lần.
4. **Không commit:** credential, model weights, dữ liệu khách hàng thật.
5. **Phải commit:** 5 file nguồn tập train mà [`merge_all.py`](offline_training/merge_all.py) cần (`train_retail_base`, `module_a_clean`, `module_b`, `module_c`, `module_d`). Hiện thiếu ⇒ **không train lại được model** ⇒ single point of failure.

---

## 7. Định nghĩa "xong"

Một việc chỉ được coi là xong khi đủ cả 7:

- [ ] Code chạy ở `ENV=LOCAL` không cần GPU
- [ ] Không vi phạm R1-R5
- [ ] Có test cho phần logic tất định; `pytest` xanh (hoặc nêu rõ cái nào đỏ và vì sao)
- [ ] Tài liệu bị ảnh hưởng đã cập nhật trong cùng PR
- [ ] Nêu được chỉ số cải thiện và cách đo
- [ ] Nêu được tác động chi phí bằng VNĐ/tháng
- [ ] `[PASSED BY MENTOR]`

---

## 8. Ưu tiên hiện tại

Theo [ARCHITECTURE.md §12](ARCHITECTURE.md):

| Thứ tự | Việc | Trạng thái |
|---|---|---|
| S0 | Tài liệu chiến lược — ARCHITECTURE.md + AGENTS.md | ✅ Xong |
| S1 | Chốt n8n làm định dạng duy nhất + bật `guided_json` + xoá vòng retry | ✅ Xong |
| S1b | Pipeline fine-tune v3 (Qwen3-8B, reverse-generation) + khôi phục data v2 | ✅ Mã xong, **cổng đo chưa chạy đủ** — xem dưới |
| S3 | Tầng tool + vòng lặp agentic + MCP bọc REST | ✅ Xong |
| S4 | Metrics `ai_metrics_log` | ✅ Xong |
| S7 | Hội thoại nhiều lượt (runtime + data đa lượt) | ✅ Xong |
| S8 | Kênh giải thích xAI (nhánh EXPLAIN) + engine báo cáo DT/CP/LN | ✅ Xong |
| **S2** | **Hạ tầng: vLLM server riêng, Qwen3-8B, ctx 32k, Redis, Cloudflare Tunnel** | 🔵 **Kế tiếp** |
| S5 | XAI hoá đơn: `reconciliation.py` + `InvoiceFieldValidator` + gộp prompt hoá đơn | ⚪ Chờ |
| S6 | Lược đồ Logistics bên Body + API xuất dòng bán/chi phí cho `/tools/report` — **cần phối hợp repo Body** | ⚪ Chặn |

Nghiệp vụ ưu tiên 1 là **logistics / báo giá vận tải**. Bán lẻ giữ lại vì code đã có, nhưng không phải đích tối ưu hoá hiện tại.

### S1b — cổng đo chất lượng chưa chạy đủ (soát 04/11/2026)

[`benchmark_v3.py`](offline_training/benchmark_v3.py) là cổng chặn chất lượng của pipeline. Nó cần bốn tập đo; **ba tập không có**:

| Tập | Có? | Sinh bằng | Cần gì |
|---|---|---|---|
| `eval_n8n.jsonl` | ✅ 34 ca | `make_n8n_eval.py` | — |
| `eval_extraction.jsonl` | ❌ | `reverse_generate.py` | `DEEPSEEK_API_KEY` |
| `eval_narration.jsonl` | ❌ | `make_narration_pairs.py` | `DEEPSEEK_API_KEY` |
| `eval_agent.jsonl` | ❌ | `make_agent_traces.py` | `DEEPSEEK_API_KEY` |

Tập duy nhất còn lại đúng là tập duy nhất sinh được không cần khoá.

**Mã nguồn xử lý chuyện này trung thực** — đây không phải lỗi che giấu. `benchmark_v3` in `"KHÔNG ĐO ĐƯỢC (thiếu dữ liệu, không phải model đạt)"`, và câu kết luận của nó có điều kiện: *"Qua mọi ngưỡng ĐO ĐƯỢC — nhưng xem hai mục ⚠ ở trên trước khi kết luận là model đạt"*. `preflight_check.py` cũng cảnh báo.

**Nhưng mã thoát vẫn là 0 khi thiếu tập đo.** Người đọc output thì hiểu đúng; một job CI đọc `$?` thì không. Hiện chưa ai đọc — `ci.yml` không gọi `benchmark_v3`. Nối nó vào CI thì phải xử chuyện này trước.

Dùng DeepSeek ở ba generator trên **không phạm R2**: chúng sinh trên kịch bản hư cấu, con số do engine thật tính, không có dữ liệu khách nào rời hệ thống. Khác hẳn [`evaluate_system.py`](src/evaluate_system.py) đã chặn — cái đó gửi dữ liệu thật đi chấm điểm.

Chi tiết và các hướng xử: xem việc trên bảng kanzo.
