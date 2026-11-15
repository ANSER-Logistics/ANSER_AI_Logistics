# SRS ANSER Brain: tình trạng và yêu cầu, 15/11/2026

| Mục | Nội dung |
|---|---|
| Ngày và commit đo | 15/11/2026, commit `f0464ed`, nhánh `feat/workflow-format-and-deterministic-core` |
| Người soạn | Agent AI (Claude), từ mã nguồn và tài liệu có sẵn trong repo. Lịch sử soạn và kiểm: Phụ lục C |
| Người chịu trách nhiệm | Chưa có. Một thành viên team Brain cần đọc, kiểm từng khẳng định mình ký, rồi ghi tên và ngày vào đây trước khi coi tài liệu là chính thức |
| Phạm vi | ANSER Brain. Body (ứng dụng nghiệp vụ của dự án) có repo tài liệu riêng; tài liệu này chỉ nêu phần Brain cần biết về Body |
| Tình trạng | Bốn lỗ hở mức P0 chưa sửa (BR-23 đến BR-26), ba việc chờ Body, năm việc chờ chủ dự án (người quyết cuối của dự án), trong đó có chọn model chạy production. Viết tắt và thuật ngữ: §12 |

## Trạng thái trong một trang

Brain là một dịch vụ web trả lời câu hỏi, đọc hoá đơn và soát sổ cho khách của dự án ANSER. Nó chạy được trên máy không có GPU, và phần tính tiền, soát sổ là code Python thuần có test. Bốn việc chưa dùng được với khách:

- Lịch sử chat không lưu được; chờ Body.
- Báo cáo từ chat thiếu nguồn dòng bán; chờ Body.
- Đọc hoá đơn bằng model thị giác chưa thử trên hoá đơn thật.
- Model chạy production chưa chốt.

Bốn lỗ hở về số liệu và dữ liệu khách (BR-23 đến BR-26) tìm ra ngày 15/11 và chưa sửa. `main`, nhánh production, thiếu 193 commit so với nhánh tính năng nơi cả team làm việc; các sửa lỗi của chu kỳ 01 và 02 chưa tới `main`.

| | Nội dung | Căn cứ |
|---|---|---|
| Chạy được | Tính tiền và soát sổ qua `/tools/*`, đọc Excel MISA, nạp và tìm trong kho tri thức. 1663 test qua ở `ENV=LOCAL` | Đo, §3 |
| Hỏng hoặc chưa nối | Lịch sử chat không lưu. Chat sang báo cáo không có nguồn dòng bán. Kết quả tác vụ mất khi khởi động lại (BR-08). `/ocr` không chạy ở `ENV=SERVER` (BR-09). Bộ kiểm số trong câu trả lời bỏ lọt số âm và số có đơn vị (BR-23). Tên khách viết thường lọt qua bộ lọc truy vấn web (BR-26) | Đo và mã, §5 |
| Bị chặn | Lịch sử chat và báo cáo chờ Body (Body#28 chưa có trả lời; Body#23). PR #25 và nhánh `feat/14-vllm-vision-client` chờ Thành rebase, không có thay đổi từ 10/11. Gộp `main`, thuê GPU, cấp `DEEPSEEK_API_KEY` chờ chủ dự án | Đo, §8 |
| Làm tiếp | Bốn việc P0 (BR-23 đến BR-26), rồi BR-29, BR-30, BR-34. BR-33: đo lại model trên Colab. Sửa ba tài liệu cũ (§10) | §6 |

Cột "Căn cứ" dùng bốn nhãn Đo, Mã, Chép, Chưa kiểm (§1.2). P0, P1, P2 là mức ưu tiên (§12). Thành (`tranthanh-riu`) và Sơn (`Dgsonn`) là thành viên team Brain.

## 1. Đọc tài liệu này thế nào

### 1.1. Người đọc và thứ tự đọc

Người đọc là thành viên mới của team Brain, biết Python, có thể chưa biết gì về AI, và chưa từng mở repo Body. Đọc xong, bạn chạy được Brain bằng `ENV=LOCAL` (§3), biết phần nào chạy được và phần nào hỏng (§5), và chọn được một việc ở §6 (cách nhận việc: §1.5).

Thứ tự đọc: §2 để hiểu sản phẩm, §3 để chạy thử, §4 và §5 để biết hệ thống ở đâu, rồi §7 để biết rủi ro trước khi chọn việc ở §6. §8 cho biết ai đang chờ ai. §10 cho biết tài liệu nào không nên tin, kể cả `SO_TAY_NGUOI_MOI.md`.

### 1.2. Căn cứ và mức chắc của từng khẳng định

Mỗi khẳng định về hiện trạng mang một trong bốn căn cứ, ghi ở cột "Căn cứ":

- Đo: lệnh ghi trong ô hoặc ở Phụ lục B đã chạy ngày 15/11/2026 trên commit `f0464ed`. Chạy lại cho cùng kết quả.
- Mã: đọc mã nguồn mà chưa chạy.
- Chép: con số do tài liệu khác ghi (`ROADMAP.md`, `BAO_CAO_BR05.md`, `AGENTS.md` §8, issue #11), chưa chạy lại.
- Chưa kiểm: chưa ai chạy hoặc đọc kỹ.

Với con số đo model, bảng ở §5.2 thêm "mức chắc" gồm bốn bậc: cao, vừa, thấp, rất thấp, mỗi bậc kèm lý do. Hai quy ước của tài liệu này: bộ câu do team viết chỉ cho mức chắc thấp khi nói về câu thật của khách, và mẫu dưới 30 câu không vượt mức thấp. Đây là quy ước của người soạn (suy luận), không phải chuẩn bên ngoài.

Ba điểm dễ nhầm:

- Test xanh cho biết các hành vi đã khoá bằng test không đổi; test xanh không chứng minh hành vi đó đúng nghiệp vụ. Ví dụ: `tests/test_freight_invoice.py` đang khoá một hành vi sai (BR-25).
- "Chưa kiểm" khác với "đã kiểm và hỏng".
- "Không có bằng chứng bản fine-tune tốt hơn" khác với "có bằng chứng bản fine-tune không tốt hơn" (§5.2).

### 1.3. Phạm vi

Tài liệu này trả lời ba câu: Brain chạy được gì, hỏng gì, và việc tiếp theo là việc nào. Nó không:

- mô tả Body (repo tài liệu riêng của Body);
- chứa tài liệu về khách pilot (nằm ở repo private khác; cần đọc thì hỏi chủ dự án);
- hướng dẫn từng bước đo hoặc huấn luyện model (xem `docs/ky-thuat/PHIEN_DO_COLAB.md`);
- thay `AGENTS.md` về cách làm việc;
- quyết thay chủ dự án các việc ở §8.

### 1.4. Tài liệu khác

| Cần biết gì | Đọc |
|---|---|
| Cách làm việc, luật code, quy trình PR | [`AGENTS.md`](../AGENTS.md) |
| Luật viết tài liệu, PR, issue | [`docs/VIET-CHO-AI-DOC.md`](VIET-CHO-AI-DOC.md) |
| Việc đang giao, ai làm | [bảng org số 6](https://github.com/orgs/ANSER-Logistics/projects/6) |
| Các chu kỳ trước | [`SRS_CHU_KY_01.md`](chu-ky-01/SRS_CHU_KY_01.md), [`SRS_CHU_KY_02.md`](chu-ky-02/SRS_CHU_KY_02.md) |
| Kiến trúc, lịch sử quyết định | [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`ROADMAP.md`](../ROADMAP.md). Cả hai lệch mã, xem §10 |

### 1.5. Nhận việc

Chọn một mục ở §6, rồi hỏi chủ dự án để được gán một issue trên bảng org số 6. Làm xong thì mở PR vào nhánh tính năng; team `brain` duyệt (`AGENTS.md` §5.0). Người chỉ có quyền đọc repo (hiện là `wikiepeidia`) phải fork trước khi mở PR.

## 2. Brain là gì

### 2.1. Sản phẩm

Brain là một dịch vụ web viết bằng FastAPI, không có giao diện. Body là ứng dụng nghiệp vụ của dự án (repo `ANSER-Logistics/ANSER-logistics-body`, giao diện viết bằng Next.js). Body gọi Brain qua HTTP khi cần trả lời câu hỏi, đọc hoá đơn, đọc bảng Excel kế toán, soát sổ hoặc tính báo giá vận tải. Dữ liệu kinh doanh gốc (hoá đơn, tồn kho, doanh số) nằm ở Body. Brain chỉ giữ tài liệu được nạp vào kho tri thức và nhật ký đo.

Khách pilot là một công ty chuyên bán dầu. Từ 12/11/2026, chu kỳ 02 chạy song song hai nghiệp vụ:

- Sổ sách và kế toán. Phần đã chạy trên dữ liệu thật của khách: đọc bảng nhập-xuất-tồn của MISA (phần mềm kế toán khách dùng), soát tồn kho, công nợ, thuế GTGT.
- Báo giá vận tải. Tính giá từ giá nhà xe, quy tắc giá và giá dầu; chọn nhà xe. Mã đã đủ và có test, chưa chạy với khách.

Bán lẻ còn trong mã vì đã viết xong, nhưng không thuộc hai nghiệp vụ của chu kỳ 02.

Theo ROADMAP (13/08, căn cứ Chép), chưa có nơi nào để khách tự truy cập Brain. Tình hình sau ngày đó chưa kiểm.

### 2.2. Nguyên tắc: code tính, model nói

Phần tính tiền và soát sổ của Brain là code Python tất định: cùng đầu vào thì cùng đầu ra, và không có model trong đường tính tiền. Model ngôn ngữ làm hai việc: diễn giải kết quả cho người đọc, và điền tham số cho công cụ mà bảng luật đã chọn. (`ARCHITECTURE.md` gọi nguyên tắc này là P1; trong tài liệu này P1 là một mức ưu tiên, xem §12.) Năm ràng buộc dưới đây là nội dung của [`AGENTS.md` §2](../AGENTS.md). Cột cuối ghi sự cố hoặc chi phí đã làm ra luật.

| Ràng buộc | Nghĩa | Sự cố hoặc chi phí |
|---|---|---|
| R1. Model không tính | Mọi con số tiền đến từ hàm Python. Thiếu dữ liệu thì nói thiếu, không điền 0. | Sự cố "phụ phí bị bỏ", sau thành yêu cầu BR-01: một phụ phí bị bỏ im lặng làm sai báo giá gửi khách. Điền 0 cho giá vốn trống làm lãi gộp bằng doanh thu, một con số sai nhưng trông như kết quả đã đo. |
| R2. Dữ liệu khách ở lại | Không gửi tồn kho, doanh thu, công nợ, bảng giá cước, danh sách khách tới model hay dịch vụ bên thứ ba. Ngoại lệ: tra cứu công khai một chiều (giá dầu, tỷ giá, tìm web) không kèm dữ liệu khách. | 27/07/2026 mật khẩu Neon (dịch vụ Postgres) bị lộ qua các script lưu trong repo công khai và phải xoay mật khẩu. |
| R3. Ngân sách | Hạ tầng pilot tối đa 5.000.000đ/tháng, mục tiêu bậc T0 khoảng 750.000đ (§4.7). PR nào tăng chi phí phải nêu số tiền, chỉ số cải thiện và nguồn trả. | Thuê GPU là khoản chi lớn nhất; §4.7 có số theo từng bậc. |
| R4. Một nguồn sự thật | Mỗi khái niệm một định nghĩa. Định dạng workflow (quy trình dạng sơ đồ gồm các node, chạy bằng n8n) duy nhất là n8n, nguồn là `src/core/workflow_schema.py`. | Danh sách node n8n từng được chép ở ba nơi và lệch nhau. |
| R5. Phần cứng qua biến môi trường | Không ghi tên GPU, số VRAM hay đường dẫn Drive trong code. Chuyển máy chỉ đổi `.env`. | Tài liệu từng ghi ba tên biến không tồn tại trong code. |

### 2.3. Bốn môi trường

Biến `ENV` chọn cách Brain chạy model:

| `ENV` | Dùng khi | Model |
|---|---|---|
| `LOCAL` | Máy dev, test | Không nạp model. Câu trả lời của model là chuỗi giả. Toàn bộ logic tất định, routing và API vẫn chạy thật. |
| `GPU` | Máy có GPU | Nạp model trong tiến trình, hoặc gọi vLLM server nếu có `VLLM_BASE_URL`. |
| `SERVER` | Triển khai bằng compose | Brain không nạp model nào, bắt buộc có `VLLM_BASE_URL`, vision tắt. |
| `COLAB` | Đo, fine-tune rời rạc | Như `GPU`. Điều khoản Colab Paid cấm phục vụ web service nên không dùng làm production. |

## 3. Chạy Brain trên máy mình

Cần Python 3.11 hoặc 3.12 (CI chạy 3.11, image Docker dùng 3.12; repo chưa khai `requires-python`). Không cần GPU. Dùng nhánh tính năng, không dùng `main`: `main` là nhánh production và thiếu 193 commit (§9).

Linux hoặc macOS:

```bash
git clone https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git
cd ANSER_AI_Logistics
git checkout feat/workflow-format-and-deterministic-core
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ENV=LOCAL uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Windows (PowerShell):

```powershell
git clone https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git
cd ANSER_AI_Logistics
git checkout feat/workflow-format-and-deterministic-core
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
$env:ENV = "LOCAL"
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Khi `uvicorn` chạy, mở `http://127.0.0.1:8000/health`. Chạy test và soát lỗi:

```bash
ENV=LOCAL python -m pytest tests/ -q -p no:randomly
python -m ruff check src tests offline_training
python -m mypy src offline_training
```

Trên PowerShell, đặt `$env:ENV = "LOCAL"` trước lệnh `pytest`. Cờ `-p no:randomly` tắt việc xáo thứ tự test để kết quả lặp lại được. `requirements-gpu.txt` chỉ dùng trên máy GPU Linux: nó kéo `vllm` và `bitsandbytes`, không cài được trên Windows.

Gọi thử một công cụ tất định (thêm `-H "X-API-Token: <token>"` nếu bạn đã đặt `API_AUTH_TOKEN`; ở `LOCAL` mặc định không đặt):

```bash
curl -s http://127.0.0.1:8000/tools/vat -H "Content-Type: application/json" -d '{"items":[{"name":"Dầu diesel","price":28000,"qty":2.5}],"stated_total":77000}'
```

Kết quả (rút gọn): `{"calculated_total":77000,"stated_total":77000,"difference":0,...,"is_valid":true,...}`. Với trường lạ, Brain trả HTTP 422 thay vì bỏ qua (`extra="forbid"`). Đó là cố ý, xem §9.

**Kết quả đo ngày 15/11/2026.** `pytest` trên nhánh tính năng cộng PR đưa tài liệu này vào: 1663 ca qua, 2 ca bị bỏ qua (1655 ca ở commit `f0464ed`, cộng 8 ca của `tests/test_srs_khop_ma.py`). Số ca lớn hơn số hàm test (1168 hàm trong 68 file `test_*.py`) vì một hàm test chạy với nhiều bộ tham số. CI chạy ít hơn khoảng 28 ca vì bước cài của CI không có `python-docx` và `pypdf` (BR-15).

## 4. Kiến trúc trong mã (commit `f0464ed`)

### 4.1. Bốn tầng

Tầng trên import tầng dưới, không ngược lại; `tests/test_layering.py` chặn import ngược (file đó gọi các tầng là T1 đến T4; tài liệu này dành chữ T cho bậc hạ tầng ở §4.7).

| Tầng | Nơi | Việc |
|---|---|---|
| Tầng 4 | `src/api/` | HTTP: route, xác thực, validate đầu vào |
| Tầng 3 | `src/agents/`, `core/engine.py`, `core/knowledge.py`, `core/memory.py` | Điều phối: router, vòng agentic, nạp model, kho tri thức |
| Tầng 2 | `src/core/` (phần còn lại) | Nghiệp vụ tất định, không biết HTTP |
| Tầng 1 | `core/config.py`, `serving.py`, `schemas.py`, `prompts.py`, `utils.py`, `nguong_p95.py`, `chunking.py` | Cấu hình và khối dùng chung |

### 4.2. Một lượt `/chat`

1. Body gọi `POST /chat` kèm `user_id`, `store_id` và câu hỏi. Brain tạo `task_id`, ghi trạng thái `processing` vào `TASK_REGISTRY` (một dict trong RAM, xem BR-08) và trả `task_id` ngay.
2. Một tác vụ nền xử lý câu hỏi. `SemanticRouter` (`src/agents/manager.py`) xếp nó vào một trong bảy nhánh:
   - `RETRIEVAL`: hỏi tài liệu nội bộ.
   - `GENERAL`: hỏi chung.
   - `DATA_INTERNAL`: tra sản phẩm, doanh số.
   - `REPORT`: báo cáo doanh thu, giá vốn, lãi.
   - `EXPLAIN`: giải thích một kết quả trước đó.
   - `TECHNICAL`: sinh workflow n8n.
   - `LOGISTICS`: yêu cầu báo giá vận tải.

   Ở `LOCAL` và `SERVER` router chỉ dùng từ khoá, vì không nạp embedder (model biến câu thành vector để so độ giống).
3. Nhánh cần số liệu chạy vòng agentic (`src/agents/agentic.py`): model và công cụ thay phiên nhau, tối đa 4 bước. `src/core/tool_planner.py` chọn công cụ bằng luật; model không chọn. Model chỉ điền tham số và viết câu trả lời. `src/core/doc_dau_vao.py` đối chiếu đầu vào của công cụ với câu của người dùng: khi model bịa ra hoặc bỏ sót một số tiền, mã gỡ số đó hoặc Brain hỏi lại người dùng.
4. Câu trả lời đi qua bộ kiểm số (`src/core/grounding.py`): mỗi con số từ 4 chữ số trở lên trong câu phải có trong kết quả công cụ. Bước này chỉ chạy ở nhánh có dữ liệu để đối chiếu; `GENERAL` và `LOGISTICS` không qua (BR-24). Bộ kiểm còn hở ở số âm và số có đơn vị (BR-23).
5. Body hỏi `GET /api/v1/task/{task_id}` để lấy kết quả. Chỉ request mang header `X-User-Id` của chủ task đọc được; Brain không xác minh header này (§7.2).

### 4.3. Một lời gọi `/tools/*`

Body gọi thẳng, không qua model. Mọi route của `/tools` dùng lược đồ pydantic `_ToolIn` (`src/api/routes/tools.py`) với `extra="forbid"`. Mỗi route kiểm token `X-API-Token` và đổi `ValueError` thành HTTP 422. `GET /tools` trả danh mục công cụ; `/mcp/tools/list` và `/mcp/tools/call` bọc cùng danh mục theo giao thức MCP.

### 4.4. Các route

`app.routes` có 29 mục: 25 route nghiệp vụ (bảng dưới) và 4 route tài liệu tự sinh của FastAPI (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`). Mọi route nghiệp vụ trừ `/health` nằm sau kiểm token (`API_AUTH_TOKEN`; để trống thì kiểm token tắt, xem §7.2). Bốn route tự sinh không kiểm token, và `/openapi.json` lộ toàn bộ lược đồ đầu vào (BR-34).

| Route | Việc |
|---|---|
| `GET /health` | Sống/chết, model đã nạp chưa, `memory_schema_error`, `auth_enabled` |
| `POST /chat` | Nhận câu hỏi, trả `task_id` |
| `GET /api/v1/task/{task_id}` | Trạng thái và kết quả của một lượt hỏi |
| `POST /upload` | Mô tả ảnh bằng model thị giác |
| `POST /ocr` | Đọc hoá đơn thành JSON rồi kiểm số học |
| `POST /ocr/freight` | Đọc hoá đơn cước vận tải của nhà xe, kiểm số học |
| `POST`, `GET`, `DELETE /knowledge/documents` | Nạp, liệt kê, xoá tài liệu trong kho tri thức của một khách |
| `POST /knowledge/search` | Tra kho, trả đoạn kèm nguồn |
| `POST /tools/quote` | Báo giá vận tải |
| `POST /tools/carrier-selection` | Xếp hạng nhà xe cho một tuyến |
| `POST /tools/forecast-reorder` | Dự báo nhu cầu và điểm đặt hàng lại |
| `POST /tools/vat` | Tính lại tổng hoá đơn và thuế GTGT |
| `POST /tools/report` | Báo cáo doanh thu, giá vốn, lãi theo kỳ |
| `POST /tools/inventory-audit`, `/tools/inventory-import` | Soát bảng tồn kho; nạp `.xlsx` MISA rồi soát |
| `POST /tools/partner-audit`, `/tools/partner-import` | Soát công nợ; nạp danh sách khách và nhà cung cấp rồi soát |
| `POST /tools/vat-catalog-audit`, `/tools/product-import` | Đối chiếu cờ thuế 8% hay 10% của danh mục hàng; nạp danh mục `.xlsx` |
| `POST /tools/period-diff` | So hai lần xuất cùng một kỳ để tìm chứng từ bị sửa hồi tố |
| `GET /tools`, `GET /mcp/tools/list`, `POST /mcp/tools/call` | Danh mục công cụ và lớp MCP |

### 4.5. Các module `src/core/`

36 file. Bảng ở §4.1 xếp theo tầng, bảng dưới xếp theo vai trò, nên một module có thể xuất hiện ở cả hai.

| Nhóm | Module |
|---|---|
| Tính toán tất định | `pricing` (báo giá), `carrier_selection`, `mcp_server` (VAT, tổng hoá đơn), `reporting` (doanh thu, giá vốn, lãi), `forecasting`, `calibration` (đối chiếu engine giá với giá đã chốt), `tax_id` (đối chiếu chữ số kiểm tra của mã số thuế) |
| Soát sổ | `inventory`, `receivables`, `period_diff`, `vat_catalog`, `freight_invoice`, `findings` (hình dạng chung của một phát hiện) |
| Đọc dữ liệu vào | `inventory_import`, `partner_import`, `doc_xlsx` (nơi duy nhất mở `.xlsx`), `doc_extract` (bóc chữ từ PDF, Word), `doc_dau_vao` (đọc đầu vào công cụ từ câu người dùng), `chunking` |
| Chốt chặn | `grounding` (bộ kiểm số trong câu trả lời), `retrieval_policy` (quy định câu trả lời được lấy từ nguồn nào, và lọc truy vấn web), `tool_planner` (chọn công cụ bằng luật) |
| Tri thức và trí nhớ | `knowledge` (kho RAG: Chroma, BM25, xếp hạng lại), `memory` (lịch sử chat), `saas_api` (truy vấn DB của Body), `context` |
| Model và workflow | `engine` (nạp model, hàng đợi tác vụ), `serving` (client vLLM, giới hạn tải), `prompts` (nguồn duy nhất của mọi system prompt), `workflow_schema` (nguồn duy nhất của định dạng n8n), `agent_middleware`, `schemas` |
| Hạ tầng | `config`, `metrics`, `nguong_p95`, `utils` |

Năm file trong `src/agents/`: `manager` (router, điều phối), `agentic` (vòng gọi công cụ), `coder` (sinh workflow n8n), `vision` (đọc ảnh), `base`.

### 4.6. Workflow n8n

n8n chạy các quy trình định kỳ và các quy trình gồm nhiều bước mà Body cần. Brain có hai nhóm tài nguyên liên quan:

- Bốn workflow viết tay trong `workflows/logistics/` cho mảng vận tải. Chưa workflow nào chạy trên n8n thật (căn cứ: chưa kiểm).
  - `fuel_price_sync`: cào giá dầu mỗi sáng vào Google Sheet.
  - `quote_request`: đọc Sheet, chọn nhà xe, tính giá, rồi gửi nháp báo giá cho chủ doanh nghiệp duyệt qua Discord.
  - `quote_approve`: khi chủ duyệt thì gửi email báo giá cho khách.
  - `debt_reminder`: nhắc công nợ quá hạn vào mỗi thứ Hai.
- 32 mẫu workflow thật của Body trong `data/n8n_templates/`, dùng làm danh mục node cho nhánh `TECHNICAL`.

Mọi mốc "hôm nay" trong các workflow này là ngày giờ Việt Nam (UTC+7). Ngày trong Google Sheet phải ở dạng `YYYY-MM-DD`.

### 4.7. Triển khai

`deploy/docker-compose.yml` khai năm dịch vụ: `vllm-text`, `vllm-vision`, `brain`, `redis`, `tunnel`. File này chưa từng được chạy; chính nó ghi như vậy ở đầu file. Chưa thuê GPU nào cho production (căn cứ: chưa kiểm ngoài `AGENTS.md` §8). `Dockerfile` chạy `--workers 1` vì `TASK_REGISTRY` còn nằm trong RAM (BR-08).

Bậc hạ tầng theo `ARCHITECTURE.md` §4.3, tính theo 26.000đ/USD. Chi phí suy ra từ giá thuê, chưa có hoá đơn thật:

| Bậc | Cấu hình | Chi phí mỗi tháng |
|---|---|---|
| T0 (pilot) | RTX 3090 thuê theo giờ làm việc, khoảng 220 giờ | khoảng 750.000đ |
| T1 | 3090 chạy 24/7 | khoảng 2.500.000đ |
| T2 | 4090 hoặc 2 × 3090 | khoảng 6.300.000đ, vượt trần |
| T3 | Máy tự sở hữu | 15 đến 18 triệu một lần, khoảng 600.000đ điện mỗi tháng |

Ở bậc T0 và bậc T1, R2 chỉ thoả một phần, vì GPU là máy thuê. Trước khi đạt T3, team không quảng cáo "dữ liệu không rời hệ thống".

## 5. Năng lực và độ chín

### 5.1. Bảng độ chín

Bốn loại: A chạy ở `ENV=LOCAL` và có test; B cần GPU hoặc model thật; C chặn bởi Body; D chưa nối hoặc đường chết. Một năng lực có thể mang hai loại (ví dụ "A logic, B chất lượng"). Cột "Căn cứ" dùng bốn nhãn ở §1.2.

| Năng lực | Loại | Hiện trạng | Căn cứ |
|---|---|---|---|
| `/tools/vat`, `/report`, `/quote`, `/carrier-selection`, `/forecast-reorder` | A | Tất định, có test. Khi giá dầu được dùng để điều chỉnh giá: cảnh báo từ 2 ngày tuổi, trả 422 từ 7 ngày. Bảng giá chưa hiệu chỉnh trên số liệu thật của khách | Đo (`pytest`); hiệu chỉnh: chưa kiểm |
| Soát sổ: tồn kho, công nợ, thuế GTGT, so hai kỳ | A | Đã chạy trên dữ liệu thật của khách pilot. Chưa có kế toán thật soát các quy tắc (§8.1) | Đo (`pytest`); chạy thật: chép từ ROADMAP |
| Đọc `.xlsx` MISA: tồn kho, đối tác, hàng hoá | A | File hỏng, rỗng hoặc thiếu sheet trả 422 (PR #61) | Đo (`tests/test_import_endpoints.py`) |
| Router và vòng agentic | A logic, B chất lượng | Công cụ do `tool_planner` chọn bằng luật. Bộ đo chọn công cụ: 6/15 (40%) ở phiên 27/10; sau khi tách ý định báo giá ngày 28/10 đo lại được 15/15, nhưng luật viết sau khi thấy bộ đề nên 100% là cận trên | Logic: đo. Con số: chép (`BAO_CAO_BR05.md` §6b) |
| Bộ kiểm số trong câu trả lời (`grounding`) | A | Hở hai chỗ (BR-23). Câu "Lãi ròng 5.000.000 đồng" qua được khi kết quả công cụ là `net_profit: -5000000`. Câu "Doanh thu đạt 45 triệu đồng" qua được dù 45 triệu không có trong kết quả | Đo (`narration_numbers_ok`, 15/11) |
| Lọc truy vấn web (`retrieval_policy`) | A | Hở tên khách viết thường (BR-26): "công ty minh long có bắt buộc xuất hoá đơn điện tử không" ra khỏi bộ lọc nguyên văn | Đo (`loc_truy_van_web`, 15/11) |
| Kho tri thức (RAG) | A nạp và tìm, B chất lượng | Embedder `BAAI/bge-m3`, xếp hạng lại `namdp-ptit/ViRanker`, chạy trên CPU mặc định. Chat dùng một workspace chung (`KB_WORKSPACE_ID`). Chưa có recall hay MRR (BR-06) | Mã; chất lượng: chưa kiểm |
| OCR hoá đơn (`/ocr`, `/ocr/freight`) | B | Cần model thị giác. Chưa thử trên hoá đơn thật. Đầu ra chưa được làm sạch (BR-19) | Mã; độ chính xác: chưa kiểm |
| Sinh workflow n8n, bóc yêu cầu báo giá, diễn giải kết quả, vòng agentic với model | B | Kết quả đo ở §5.2 | Chép (`BAO_CAO_BR05.md` §6d) |
| Lịch sử chat nhiều lượt | C | `memory.py` đọc 6 bảng mà Body không có. Mọi hàm bắt lỗi và trả rỗng, nên chat chạy nhưng không nhớ gì. Hướng đã chốt: Body gửi kèm `history`; Body chưa trả lời | Chép (issue #11 và #19: 15 migration, 13 bảng, đo lại trên `schema.ts` ngày 07/11) |
| Chat sang báo cáo (`REPORT`) | C | `saas.get_report_lines` không tồn tại. Body có sẵn `collectSaleLines` cho giao diện của họ nhưng chưa có bảng chi phí (Body#23) | Mã |
| Giải thích kết quả (`EXPLAIN`) | C, chờ lịch sử chat | Tìm khối JSON của engine trong lịch sử chat, mà lịch sử không lưu được | Mã |
| `DATA_INTERNAL` | A một phần | Truyền nguyên câu hỏi vào điều kiện `LIKE` khi tra sản phẩm, nên câu hỏi tự nhiên hiếm khi khớp | Mã |
| Metrics và p95 | D | Ghi vào file JSONL cục bộ; p95 tính ra nhưng không nối vào `/health` (BR-10) | Đo (`/health` không có trường p95) |
| Tác vụ nền qua Redis | D | `TASK_REGISTRY` còn trong RAM (BR-08) | Đo (`REDIS_URL` không có trong `src/`) |
| Client HTTP cho vision | D | Compose có container `vllm-vision` nhưng không có mã gọi nó (BR-09) | Đo (`VLLM_VISION_BASE_URL` không có trong `src/`) |
| Cổng đo chất lượng model (`benchmark_v3`) | B | Có 1 trong 4 tập đo; ba tập còn lại cần `DEEPSEEK_API_KEY` | Chép (`AGENTS.md` §8) |

### 5.2. Kết quả đo model

Hai model cùng so: model gốc (Qwen3-8B, bản AWQ chính thức) và bản fine-tune (cùng Qwen3-8B, huấn luyện thêm bằng dữ liệu của dự án). Phiên so cặp ngày 29/10/2026, cùng commit, cùng phiên, cùng cấu hình (vLLM 0.11.2, GPU L4, ngữ cảnh 32768), trên bộ câu hỏi do team viết (`BAO_CAO_BR05.md` §6d). Cột "sửa" là số câu bản fine-tune đúng mà model gốc sai; cột "hỏng" là số câu ngược lại. p là xác suất thấy chênh lệch lớn như vậy nếu hai model thật ra ngang nhau (phép kiểm McNemar chính xác trên các câu hai model làm khác nhau); dưới 0,05 thì coi là có khác biệt.

| Nhiệm vụ | Số câu | Model gốc | Bản fine-tune | Sửa / hỏng | p | Mức chắc và lý do |
|---|---|---|---|---|---|---|
| Bóc yêu cầu báo giá | 98 | 0/98 (0,0%) | 63/98 (64,3%; Wilson 95%: 54,4% đến 73,1%) | 63 / 0 | gần 0 | Cao cho chiều khác biệt trên bộ này: 63 câu một chiều, 0 câu ngược. Thấp cho khách thật: bộ câu sinh từ kịch bản hư cấu |
| Sinh workflow n8n | 34 | 10/34 (29,4%) | 30/34 (88,2%) | 21 / 1 | 0,00001 | Cao cho chiều khác biệt trên bộ này. Phiên 15/08 cho kết quả khác (50,0% so với 67,6%, p = 0,24) vì khung đo lúc đó có lỗi |
| Diễn giải kết quả | 27 | 21/27 (77,8%; Wilson 95%: 59,2% đến 89,4%) | 17/27 (63,0%) | 3 / 7 | 0,34 | Rất thấp để kết luận bản nào hơn: p lớn, 27 câu, khoảng tin cậy rộng 30 điểm. Trong 7 câu hỏng có 6 câu bị cắt cụt do suy biến, đã thêm chốt suy biến ở production |
| Vòng agentic | 19 | 15/19 (78,9%) | 16/19 (84,2%) | 1 / 0 | 1,0 | Rất thấp: 19 câu, chênh lệch 1 câu. Bảng luật chọn công cụ giữ an toàn cho cả hai bản |

Căn cứ của cả bảng: Chép, với p và khoảng Wilson tự tính lại (Phụ lục B). Bốn điểm giới hạn:

- Phiên 15/08 (`ROADMAP.md`) cho số khác ở ba nhiệm vụ cuối (diễn giải: gốc 85,2%, fine-tune 44,4%, p = 0,001; agentic: gốc 52,6%, fine-tune 15,8%, p = 0,039). `BAO_CAO_BR05.md` ghi rằng bộ đo 15/08 đã đổi nhiều chỗ (payload, grammar, cách chấm agentic) nên chỉ dùng để định hướng. Tài liệu này dùng phiên 29/10.
- Cả hai phiên chạy trên câu do team viết, không phải câu thật của khách. Chưa có phép đo nào trên câu thật.
- Mã đã đổi sau 29/10 (chốt đầu vào, chốt suy biến, tách ý định báo giá), và chưa có phiên đo nào chạy lại sau các thay đổi đó.
- Ở diễn giải, bản fine-tune bịa số ở 1 câu và bản gốc ở 6 câu (cộng 9 câu của bản fine-tune bị cắt cụt nên không chấm được số). Mỗi model chạy một lần; `BAO_CAO_BR05.md` ghi rằng cùng một cấu hình, hai lần chạy cho 9 và 13 câu cắt cụt, nên dao động giữa các lần chạy lớn.

## 6. Yêu cầu chức năng

Mỗi yêu cầu có ba phần theo khuôn của SRS chu kỳ 01: vì sao, yêu cầu, nghiệm thu bằng lệnh hoặc kết quả quan sát được. Phần "ngoài yêu cầu" chỉ ghi khi có. Mức ràng buộc dùng bốn từ: PHẢI, NÊN, CÓ THỂ, KHÔNG ĐƯỢC. Trạng thái ghi ngày 15/11/2026; bảng org số 6 cho biết ai đang làm việc gì.

### 6.1. Đã xong

| Mã | Việc | Bằng chứng |
|---|---|---|
| BR-01 | `/tools` từ chối trường lạ | `_ToolIn` có `extra="forbid"`; `python offline_training/doi_chieu_hop_dong_body.py` thoát 0 |
| BR-02, BR-03 | Đường chat dùng được vLLM server; `engine` chọn backend theo biến môi trường | `tests/test_engine_backend.py` |
| BR-04, BR-05 | Đo vLLM trên L4 và ngân sách ngữ cảnh; phân loại lỗi bản fine-tune | `docs/chu-ky-01/BAO_CAO_BR04.md`, `BAO_CAO_BR05.md` |
| BR-07 | CI soát lint cả `src`, `tests` và `offline_training` | `.github/workflows/ci.yml` |
| BR-13 | Tách `requirements-gpu.txt` khỏi `requirements.txt` | PR #57. Đo bằng `pip --dry-run`: dung lượng tải về giảm từ 5,31 GB xuống 0,43 GB. Chưa chạy `docker build` thật |
| BR-16 | Test cho `unit_cost_of` và hai endpoint nhập Excel | PR #60 và #61 |
| BR-17 | Nhà xe có nhiều giá chào thì bị loại, giá sau không đè giá trước | PR #59. Hai giá giống hệt nhau chưa được gộp, xem BR-31 |

### 6.2. Còn mở từ chu kỳ 02

Phần vì sao, yêu cầu và nghiệm thu của các mã dưới đây nằm ở [`SRS_CHU_KY_02.md` §3](chu-ky-02/SRS_CHU_KY_02.md). Không chép lại ở đây để hai bản không lệch nhau.

| Mã | Ưu tiên | Việc | Người | Issue | Trạng thái 15/11 |
|---|---|---|---|---|---|
| BR-08 | P0 | Trạng thái tác vụ nền qua Redis | Thành | [#15](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/15), PR #25 | Mã đã viết. PR xung đột `.github/workflows/ci.yml` với nhánh tính năng, chưa rebase từ 10/11 |
| BR-09 | P0 | Client HTTP cho `vllm-vision` | Thành | [#14](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/14) | Nhánh `feat/14-vllm-vision-client` đã đẩy, chưa mở PR, xung đột `src/core/engine.py` |
| BR-10 | P1 | Nối ngưỡng p95 vào `/health` | Thành | [#9](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/9) | Chưa bắt đầu. Đã chốt: cửa sổ 200 lượt, tối thiểu 30 mẫu, chỉ ngưỡng ms/token hạ `degraded` |
| BR-06 | P1 | Bộ đo RAG (recall, MRR) | Thành | [#34](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/34) | Chưa bắt đầu (`offline_training/do_rag.py` chưa có) |
| BR-11 | P1 | Compose nhất quán với phần còn lại | Thành | [#35](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/35) | Chưa làm. Compose còn ghim vLLM `v0.8.5` và `--quantization=awq` |
| BR-12 | P2 | Ghim nhóm gói AI | Thành | [#13](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/13) | Cần một phiên Colab có GPU. 14 gói còn trong `CHUA_GHIM` |
| BR-14 | P1 | Gỡ ghim `fastapi<0.137` | Sơn | [#30](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/30) | Chưa làm. `requirements.txt` còn ghim |
| BR-15 | P1 | CI đỏ khi có ca skip chưa khai báo | Sơn | [#29](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/29) | Chưa làm. CI chưa cài `python-docx` và `pypdf` |
| BR-18 | P2 | Biến môi trường code đọc mà `.env.example` không ghi | Sơn | [#38](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/38) | Chờ BR-09, vì cùng sửa `deploy/.env.example` |
| BR-19 | P1 | Làm sạch đầu ra model thị giác | agent (`PCBoiz`) | [#39](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/39) | Chưa có mã |
| BR-20 | P2 | `/health` phân biệt "chưa cấu hình DB" với "khoẻ" | agent (`PCBoiz`) | [#19](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/19) liên quan | Một phần: `/health` đã có `memory_schema_error` và tính nó vào `degraded`. Còn thiếu trường hợp không đặt `DATABASE_URL` |
| BR-21 | P2 | Chạy lại từng bước của `SO_TAY_NGUOI_MOI.md` trên máy sạch | Sơn | [#18](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/18) | Làm sau khi sổ tay được sửa (§10) |

### 6.3. Việc phát hiện ngày 15/11

BR-22 đến BR-34 phát hiện ngày 15/11. BR-33 đã giao Thành; các mục còn lại chưa có người nhận. Bốn mục đã có dấu vết ở nơi khác:

- BR-23, phần số có đơn vị, trùng với issue [#10](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/10). Hàm `narration_numbers_ok` đã có cờ `chi_kiem_so_tien` (mặc định tắt, không nơi nào trong `src/` bật; chờ chủ dự án duyệt). Phần dấu âm chưa có gì.
- BR-26 nằm ở mục 9 của issue [#11](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/11).
- BR-25 đã có một commit sửa (`ee97990`) trên nhánh `fix/hoa-don-cuoc-vat-chua-doc-khac-0`, chưa mở PR, chưa ai duyệt.
- BR-24 chưa có gì.

Lệnh nghiệm thu chung là `ENV=LOCAL python -m pytest tests/ -q -p no:randomly`. Test mới của mỗi mục phải đỏ trên mã cũ, và phải đỏ vì đúng lỗi mà mục đó mô tả.

#### BR-22. Mốc "hôm nay" theo giờ Việt Nam ở bốn file chưa sửa

Ưu tiên P1.

**Vì sao.** Máy chủ chạy theo UTC (chưa kiểm máy production). Từ 00:00 đến 07:00 sáng ở Việt Nam, `date.today()` còn trả ngày hôm qua, nên báo cáo "hôm nay" và ngày hiệu lực của tài liệu lệch một ngày. PR #54 đã sửa `pricing` và ba workflow n8n. Bốn file còn lại:
- `saas_api.py`: ba điều kiện SQL dùng `CURRENT_DATE` và `date_trunc`, tính theo múi giờ của phiên DB.
- `knowledge.py` (dòng 497): ngày hiệu lực tài liệu.
- `prompts.py` (dòng 291).
- `reporting.py`: chỉ có một chú thích và trường `ReportRequest.today` mà không mã nào đọc.

**Yêu cầu.**
1. Mọi chỗ tính "hôm nay" PHẢI dùng một định nghĩa duy nhất: `pricing.hom_nay_vn()`, hoặc bản chuyển sang `utils.py` nếu import từ `pricing` gây ngược tầng (`tests/test_layering.py`).
2. Người nhận việc PHẢI xoá trường `ReportRequest.today` hoặc nối nó với `hom_nay_vn()`.
3. Các dấu thời gian là thời điểm cụ thể (`computed_at`, `ts` của metrics) KHÔNG ĐƯỢC đổi: chúng ở UTC và không có nghĩa "hôm nay".

**Nghiệm thu.** Với đồng hồ giả ở 20:00 UTC, `saas_api.py`, `knowledge.py` và `prompts.py` đều trả ngày hôm sau. Lệnh `grep -rnE "date\.today\(\)|CURRENT_DATE" src/` không còn dòng nào ngoài định nghĩa của `hom_nay_vn`.

#### BR-23. Bộ kiểm số bỏ qua dấu âm và số có đơn vị

Ưu tiên P0.

**Vì sao.** Hai kiểu sai lọt qua `src/core/grounding.py`. Một: bộ đọc số bỏ qua dấu trừ, nên câu "Lãi ròng 5.000.000" khớp với kết quả `net_profit: -5000000`, tức lỗ bị nói thành lãi. Hai: bộ kiểm chỉ giữ số có từ 4 chữ số, và loại các số ngắn trước khi nhân đơn vị. "45" trong "45 triệu" chỉ có 2 chữ số nên bị loại trước khi đổi thành 45.000.000, và không bao giờ được so với kết quả công cụ. Câu "3,96 tỷ" do model bịa cũng lọt như vậy.

**Yêu cầu.**
1. Khi kết quả công cụ là số âm mà câu trả lời nêu số dương tương ứng kèm một từ chỉ chiều (lãi, lỗ, tăng, giảm), `grounding` PHẢI chặn câu đó.
2. `grounding` PHẢI quy số có đơn vị (nghìn, triệu, tỷ) ra đồng rồi mới đối chiếu.
3. Người nhận việc PHẢI đo tỷ lệ câu đúng bị chặn nhầm trước và sau khi sửa, trên các cặp (câu trả lời, ngữ cảnh) có trong `tests/` và `offline_training/`, kèm danh sách từng ca đổi kết quả. Bộ đo là câu do người trong team viết, không phải câu trả lời thật; PR phải ghi rõ điều đó.

**Nghiệm thu.** Test mới cho hai ví dụ trên. Mọi test hiện có của `grounding` vẫn xanh.

**Ngoài yêu cầu.** Không gộp ba bộ đọc số tiền (BR-32).

#### BR-24. Prompt `GENERAL` và `RETRIEVAL` bảo model "có phép tính thì tính"

Ưu tiên P0.

**Vì sao.** `src/core/prompts.py` (dòng 77 và dòng 90) dạy model đúng điều R1 cấm. Nhánh `GENERAL` cũng không qua bộ kiểm số (§4.2), nên con số do model tự tính đi thẳng tới khách.

**Yêu cầu.**
1. Prompt PHẢI dạy: model không tự tính; khi câu cần phép tính tiền hoặc thuế, model nói cần dùng công cụ tính và hỏi lại dữ kiện còn thiếu.
2. Prompt KHÔNG ĐƯỢC hứa thứ hệ thống không làm. Người nhận việc PHẢI kiểm xem hai nhánh này có đường chạy công cụ không trước khi viết lời hứa.
3. Prompt PHẢI nằm trong `prompts.py` (`AGENTS.md` §4.1, quy tắc 7).

**Nghiệm thu.** Test khoá nội dung: prompt không chứa lời bảo tính, có chỉ dẫn từ chối tự tính. PR phải ghi rằng việc này đổi cách trả lời khách ở các câu có phép tính.

#### BR-25. `freight_invoice.py` coi hoá đơn cước không đọc được VAT là VAT 0%

Ưu tiên P0. Đã có nhánh sửa (đầu §6.3).

**Vì sao.** `src/core/freight_invoice.py` trả `ok: True` khi không đọc được thuế, và `tests/test_freight_invoice.py` đang khoá hành vi đó. Hệ thống trình bày "chưa đọc được" như "thuế 0%", một con số trông như đã đo.

**Yêu cầu.**
1. Khi không đọc được VAT, `freight_invoice.py` PHẢI trả kết quả khác với "VAT 0%", và KHÔNG ĐƯỢC trả `ok: True`.
2. PR PHẢI chọn một trong hai cách nói thiếu ở `AGENTS.md` §2 (R1) và giải thích lựa chọn dựa trên hợp đồng API mà Body khai cho `/ocr/freight` (danh sách trường Body gửi và nhận). Cách một: trả đủ khoá kèm giá trị tự nói "chưa biết", như `reporting.build_report`. Cách hai: bỏ hẳn khoá, như `validate_invoice_total`.
3. Người nhận việc PHẢI sửa test trong `tests/test_freight_invoice.py` đang khoá hành vi `ok: True` khi không đọc được thuế, và nêu lý do.

**Nghiệm thu.** Sau khi sửa, `python offline_training/doi_chieu_hop_dong_body.py` vẫn thoát 0, nghĩa là mọi trường Body gửi cho `/ocr/freight` vẫn được Brain nhận. Một test mới khẳng định "chưa đọc được VAT" khác "VAT 0%".

#### BR-26. Tên khách viết thường rời hệ thống qua truy vấn web

Ưu tiên P0, ràng buộc R2.

**Vì sao.** `retrieval_policy.py` chỉ xoá chuỗi từ viết hoa đứng sau từ đánh dấu đối tác ("công ty", "khách"). Câu "công ty minh long có bắt buộc không" đi nguyên văn tới DuckDuckGo.

**Yêu cầu.**
1. Sau từ đánh dấu, `retrieval_policy` PHẢI xoá tối đa 3 từ viết thường không có trong danh sách từ thông dụng (từ chức năng như "của", "là", "có", và các cụm như "bắt buộc", "kê khai"). Gặp từ thứ 4 thì PHẢI không gửi truy vấn đi (trả chuỗi rỗng), vì một lần tra web hụt rẻ hơn một tên khách rò ra ngoài.
2. Từ đánh dấu (công ty, khách hàng) PHẢI nhận cả dạng không dấu ("cong ty", "khach hang").
3. Danh sách từ thông dụng PHẢI khớp theo dấu chính xác. Nếu so khớp sau khi bỏ dấu, "mình" khớp "minh" và "đang" khớp "Đặng".
4. Log KHÔNG ĐƯỢC chứa nội dung truy vấn.

**Nghiệm thu.** Tỷ lệ câu đúng bị chặn nhầm do lớp này không quá 1% trên các câu hỏi công khai có sẵn trong repo (`tests/`, `offline_training/seed_prompts.jsonl`, `offline_training/v2_sources/`); PR PHẢI ghi từng ca đổi. Mọi test hiện có của `tests/test_retrieval_policy.py` vẫn xanh.

**Ngoài yêu cầu.** Tên không đứng sau từ đánh dấu ("minh long có phải nộp thuế không") vẫn lọt qua bộ lọc. PR PHẢI ghi điều đó trong docstring.

#### BR-27. Không chặn event loop

Ưu tiên P1, theo `AGENTS.md` §4.1 quy tắc 2.

**Vì sao.** Handler `async` gọi hàm đồng bộ tốn thời gian (embedding, tìm web, SQL, đọc xlsx) thì cả server đứng hình trong lúc đó: `/health` và `GET /api/v1/task/{task_id}` đều chờ.

**Yêu cầu.** Người nhận việc PHẢI làm ba PR theo thứ tự:
1. PR-A: chuyển các hàm không dùng chung trạng thái sang `asyncio.to_thread`. Năm chỗ: `web_search_fallback` (định nghĩa ở `src/api/dependencies.py`, gọi ở `chat.py`), `doc_extract.extract` trong `src/api/routes/knowledge.py`, và ba loader xlsx trong `tools.py`. Nhánh `fix/khong-chan-event-loop-a` đã có mã, thiếu test.
2. PR-B: chuyển bốn hàm SQL (`_load_history`, `_save_turn`, `lookup_product`, `get_sales_report`) sang `asyncio.to_thread`. Handler PHẢI `await` `_save_turn` để giữ thứ tự ghi trước đọc.
3. PR-C: mọi truy cập `KnowledgeBase` đi qua một `ThreadPoolExecutor(max_workers=1)`, chuyển cả năm chỗ gọi (`chat.py` một chỗ, `routes/knowledge.py` bốn chỗ) trong cùng một PR. Chuyển nửa vời tạo ra chính lỗi tranh chấp (race condition) cần tránh: khi nạp lại tài liệu cùng nguồn, đoạn (chunk) chứa giá cũ có thể tồn tại cạnh bản mới.

Cả ba PR KHÔNG ĐƯỢC dùng `asyncio.Lock` ở mức module. Cả ba KHÔNG ĐƯỢC đặt `wait_for` trên đường kho tri thức: hết giờ sẽ thành danh sách rỗng, và câu trả lời ra "không có tài liệu" cho tài liệu có thật.

**Nghiệm thu.** Một coroutine tick mỗi 10 ms chạy song song với request có một hàm chặn 300 ms (đã monkeypatch). Khoảng trễ lớn nhất giữa hai tick phải dưới 0,15 giây; với mã cũ, suy ra khoảng 0,3 giây (chưa đo). `ValueError` vẫn ra 422, `RuntimeError` vẫn ra 503. `tests/test_layering.py` xanh.

**Ngoài yêu cầu.** `SemanticRouter` chạy embedder trên event loop ở `ENV=GPU`. Chưa đo nên chưa đưa ra thread.

#### BR-28. Luồng n8n báo giá không có nhánh báo lỗi

Ưu tiên P1. Cần người có instance n8n để chạy thử.

**Vì sao.** Lỗi trong `quote_request`, kể cả 422 do giá dầu cũ từ 7 ngày, chỉ nằm trong lịch sử thực thi của n8n; chủ doanh nghiệp không nhận cảnh báo nào. Hai node gọi Brain còn bật `retryOnFail` dù lỗi 4xx không tự khỏi.

**Yêu cầu.**
1. Hai node gọi Brain PHẢI tắt thử lại với lỗi 4xx.
2. Luồng PHẢI có nhánh lỗi báo Discord cho chủ doanh nghiệp, kèm nội dung `detail` của Brain.
3. Khi nhánh lỗi chạy, luồng PHẢI trả lời webhook gốc bằng mã HTTP lỗi và không kèm `draft_id`, để `chat.py` báo "chưa xác nhận" cho khách.
4. Logic ngưỡng giá dầu KHÔNG ĐƯỢC chuyển vào n8n (R4).

**Nghiệm thu.** Test cấu trúc đọc file JSON: nhánh lỗi nối tới node Discord, không còn `retryOnFail` ở hai node. Chưa ai chạy thử luồng này trên n8n thật; việc đó chưa có lệnh nghiệm thu.

#### BR-29. `VLLM_BASE_URL` không giới hạn host

Ưu tiên P1, ràng buộc R2.

**Vì sao.** Chỉ cần đặt một biến môi trường (`VLLM_BASE_URL`) là mọi prompt, kể cả prompt chứa dữ liệu khách, đi tới một dịch vụ công cộng. `serving.py` đọc biến này mà không kiểm gì.

**Yêu cầu.**
1. Khi host của `VLLM_BASE_URL` không thuộc localhost, dải mạng riêng (10/8, 172.16/12, 192.168/16) hoặc tên dịch vụ không có dấu chấm như `vllm-text` trong compose, `serving.py` PHẢI từ chối, kèm thông báo lỗi nêu tên biến.
2. `serving.py` PHẢI từ chối host đánh lừa như `127.0.0.1.evil.com` và URL có `user:pass@`.
3. Mã KHÔNG ĐƯỢC thêm biến cho phép host ngoài. Thêm công tắc đó là đổi cách quản lý cấu hình bảo mật và cần chủ dự án quyết trước (`AGENTS.md` R2b, mục 3).

**Nghiệm thu.** Test bảng host hợp lệ và không hợp lệ. Giá trị `VLLM_BASE_URL` trong `deploy/docker-compose.yml` vẫn được chấp nhận.

#### BR-30. Thuế suất 8%/10% và số lượng do model chọn, không ai kiểm

Ưu tiên P1. Một phần cần chủ dự án quyết.

**Vì sao.** Khi gọi công cụ `vat`, model tự điền `is_reduced_vat` và `qty`. Câu của người dùng có thể không nói thuế suất hay số lượng, và `mcp_server.py` dùng `default_is_reduced` mà không báo cho ai (chưa kiểm có ghi log hay không).

**Yêu cầu.**
1. Khi câu của người dùng không nói thuế suất hay số lượng, `doc_dau_vao.py` PHẢI gỡ giá trị model tự điền cho `is_reduced_vat` và `qty`, dùng bộ đối chiếu có sẵn. Cách khác được chấp nhận: Brain hỏi lại người dùng theo cơ chế hỏi lại có sẵn.
2. Khi mặt hàng có trong danh mục, mã PHẢI đối chiếu với `vat_catalog` và ưu tiên danh mục.
3. Nếu cần chọn chính sách thuế suất mặc định, người làm PHẢI dừng và hỏi chủ dự án.

**Nghiệm thu.** Test: câu không nói thuế suất thì tham số model điền bị gỡ; mặt hàng có trong danh mục thì dùng thuế suất của danh mục.

#### BR-31. Hai giá chào giống hệt thì gộp làm một

Ưu tiên P2. Chủ dự án uỷ quyền chốt ngày 15/11.

**Vì sao.** PR #59 loại mọi nhà xe có hơn một giá chào. Hai dòng trùng y hệt (cùng nhà xe, cùng giá) là dữ liệu nhập lặp, không có gì để chọn giữa chúng, nên loại chúng là chặn nhầm.

**Yêu cầu.** Khi một nhà xe có nhiều giá chào giống hệt nhau, `_gom_gia_chao` (`carrier_selection.py`) PHẢI gộp chúng làm một. Khi các giá chào khác nhau, nó PHẢI vẫn loại nhà xe đó, với lý do liệt kê các giá khác nhau.

**Nghiệm thu.** Với hai dòng giống hệt, `select_carrier` xếp hạng nhà xe như khi nhà xe chỉ có một giá chào. Với ba dòng, hai giống và một khác, nó loại nhà xe. `tests/test_carrier_selection_trung_gia.py` xanh sau khi sửa ca nào đang khoá hành vi cũ.

#### BR-32. Ba bộ đọc số tiền tiếng Việt cùng tồn tại

Ưu tiên P2, ràng buộc R4. Chờ đo trên câu thật.

**Vì sao.** `grounding`, `doc_dau_vao` và `retrieval_policy` mỗi nơi có một bộ đọc số tiền, và chúng lệch nhau ở "5 trăm nghìn" và "hai ty ruoi" (căn cứ: đo trên bộ lọc web ngày 15/11; hai bộ còn lại chưa kiểm riêng). Nếu gộp ba bộ thành một, cách `doc_dau_vao` hỏi lại khách sẽ đổi, nên cần đo trên câu thật của khách trước khi gộp.

**Yêu cầu.** Người nhận việc PHẢI hỏi chủ dự án nguồn câu thật và quy tắc ẩn danh trước khi thu câu (R2), vì Brain không lưu lịch sử chat. Sau đó PHẢI chạy ba bộ đọc trên các câu đã ẩn danh và báo các ca cho kết quả khác nhau. Việc đo chưa phải việc gộp.

**Nghiệm thu.** Bảng các ca mà ba bộ đọc cho kết quả khác nhau, kèm đề xuất bộ nào đúng. Chưa có lệnh sinh bảng; người nhận việc viết kèm một script trong `offline_training/`.

#### BR-33. Đo lại model và chốt model chạy production

Ưu tiên P1. Cần một phiên Colab có GPU; giao Thành. Phụ thuộc `DEEPSEEK_API_KEY` cho ba tập đo còn thiếu (§8.1).

**Vì sao.** §8.2 liệt kê các tài liệu mâu thuẫn nhau. Phiên so cặp gần nhất (29/10) đã chạy cả bốn nhiệm vụ, nhưng trước các thay đổi mã sau đó (§5.2).

**Yêu cầu.**
1. Người nhận việc PHẢI đo lại model gốc và bản fine-tune trên cùng bộ câu hỏi cho cả bốn nhiệm vụ ở §5.2. Mỗi con số PHẢI kèm số câu hỏng và số câu sửa, không chỉ tỷ lệ phần trăm.
2. Nếu phương án đề xuất cần chạy hai model cùng lúc, PHẢI nêu chi phí VNĐ/tháng (R3).
3. Người nhận việc KHÔNG ĐƯỢC tự chọn model: chọn là quyết định của chủ dự án.

**Nghiệm thu.** `offline_training/benchmark_v3.py` chạy ra bảng cho các nhiệm vụ; tập đo nào chưa có thì bảng nói thẳng là chưa đo được.

#### BR-34. Route tài liệu tự sinh của FastAPI không kiểm token

Ưu tiên P1, ràng buộc R2.

**Vì sao.** Khi đặt `API_AUTH_TOKEN`, `/tools` trả 401 nhưng `/openapi.json`, `/docs` và `/redoc` vẫn trả 200 (đo ngày 15/11 bằng `TestClient`). `/openapi.json` lộ toàn bộ lược đồ đầu vào của mọi route cho người không có token.

**Yêu cầu.** Khi `ENV` khác `LOCAL`, ứng dụng PHẢI tắt `/docs`, `/redoc` và `/openapi.json`, hoặc đặt chúng sau `auth_guard`. Sửa nằm ở `src/api/main.py`, file đang bị PR #25 và nhánh `feat/14-vllm-vision-client` giữ; làm sau khi hai nhánh đó gộp.

**Nghiệm thu.** Với `API_AUTH_TOKEN` đặt và `ENV=SERVER`, ba route trên trả 401 hoặc 404; `/health` vẫn trả 200.

## 7. Rủi ro đã biết

### 7.1. Khách có thể thấy con số sai

| Rủi ro | Nơi | Xử bằng |
|---|---|---|
| Số có đơn vị do model bịa không bị kiểm, số âm bị đọc thành dương | `grounding` | BR-23 |
| Câu trả lời của `GENERAL` không qua bộ kiểm số, và prompt bảo model tính | `prompts.py`, `chat.py` | BR-24 |
| Model chọn thuế suất và số lượng, không ai kiểm | `doc_dau_vao`, `mcp_server` | BR-30 |
| Hoá đơn cước không đọc được VAT vẫn `ok` | `freight_invoice` | BR-25 |
| Quy tắc kế toán (bảng 8%/10%, phát hiện sửa hồi tố, cảnh báo khi một khách chiếm 20% hoặc 50% tổng công nợ) do chính team đặt, chưa có kế toán thật soát | `vat_catalog`, `period_diff`, `receivables` | Chờ chủ dự án tìm người soát (§8.1) |
| "Hôm nay" theo UTC ở bốn file | `saas_api`, `knowledge`, `reporting`, `prompts` | BR-22 |
| Giá dầu cũ làm báo giá lệch | `pricing` | Đã có ngưỡng 2 và 7 ngày (PR #55) |
| Model chạy production chưa chốt (§8.2) | `ARCHITECTURE`, compose | BR-33 |

### 7.2. Dữ liệu có thể rời hệ thống

| Rủi ro | Nơi | Xử bằng |
|---|---|---|
| Tên khách viết thường đi tới DuckDuckGo | `retrieval_policy` | BR-26 |
| `VLLM_BASE_URL` trỏ ra ngoài thì mọi prompt đi ra ngoài | `serving.py` | BR-29 |
| `API_AUTH_TOKEN` để trống thì mọi route nghiệp vụ mở; chỉ `/health.auth_enabled` cho biết | `dependencies.py` | Chưa có mã BR. Cần quyết định (chủ dự án): từ chối khởi động khi `ENV` khác `LOCAL` mà không có token |
| Bốn route tài liệu tự sinh không kiểm token, `/openapi.json` lộ lược đồ | `main.py` | BR-34 |
| Một token chung cho mọi caller; `user_id`, `store_id` lấy từ header hoặc body mà không xác minh | `dependencies.py` | Chưa có mã BR |
| Chat dùng một workspace tri thức chung | `chat.py` | Đủ cho một khách; thành rò chéo khi có khách thứ hai |
| Dữ liệu khách nằm lại trên đĩa máy GPU thuê (Chroma, metrics) | `knowledge.py`, `metrics.py` | Chưa có mã BR; `ARCHITECTURE.md` §4.3 ghi biện pháp "không để lại" nhưng chưa có mã |
| Đầu ra model thị giác chưa làm sạch | `vision`, `/ocr` | BR-19 |

### 7.3. Hỏng mà không ai biết

| Rủi ro | Nơi | Xử bằng |
|---|---|---|
| Lịch sử chat không lưu được, mọi hàm trả rỗng | `memory.py` | Chờ Body; `/health.memory_schema_error` đã báo |
| Kết quả tác vụ mất khi khởi động lại | `engine.py` | BR-08 |
| Luồng n8n báo giá chết im lặng | `logistics_quote_request.json` | BR-28 |
| Server đứng hình khi một handler gọi hàm chặn | `chat.py`, `knowledge.py`, `tools.py` | BR-27 |
| `/ocr` trả HTTP 200 kèm `success: false` khi lỗi | `documents.py` | Đề xuất: Body đọc trường `success`. Chưa có mã BR |
| Callback về Body chỉ ghi log khi thất bại | `chat.py` | Chưa có mã BR |
| CI bỏ qua im lặng các ca đọc Word và PDF; `benchmark_v3` thoát 0 khi thiếu tập đo | `ci.yml`, `benchmark_v3.py` | BR-15; cờ `--doi-du-tap-do` đã có, chưa nối vào CI |
| `main` thiếu 193 commit so với nhánh tính năng, nên nhánh production thiếu mọi sửa R1 và R2 của hai chu kỳ | git | Chủ dự án quyết thời điểm gộp |

## 8. Đang chờ ai

### 8.1. Chủ dự án

- Gộp nhánh tính năng vào `main`. Theo `AGENTS.md` §6.0 chỉ chủ dự án quyết, vì `main` là nhánh production.
- Cấp `DEEPSEEK_API_KEY` để sinh ba tập đo còn thiếu của `benchmark_v3` (sinh trên kịch bản hư cấu, không phạm R2).
- Thuê GPU; chọn cách để khách truy cập Brain từ bên ngoài; chọn nơi chạy n8n. Các quyết định này tốn tiền (R3); §4.7 mới có số cho GPU.
- Tìm người kế toán soát các quy tắc ở §7.1.
- Gửi yêu cầu xoá các commit cũ tới GitHub Support (issue [#63](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/63)).

### 8.2. Model chạy production

Các tài liệu mâu thuẫn, và chủ dự án chưa xác nhận:

- `ROADMAP.md` (đo ngày 15/08) kết luận dùng model gốc. Bộ đo 15/08 sau đó được ghi nhận là có lỗi (`BAO_CAO_BR05.md` §2), nên kết luận này lỗi thời.
- `BAO_CAO_BR05.md` §6d và `BIEN_BAN_CHU_KY_01.md` §1 (29/10) kết luận giữ bản fine-tune: trên bốn nhánh, bản fine-tune làm hỏng 8 câu và sửa 88 câu.
- `docker-compose.yml` nạp bản fine-tune (`anser-v3`).
- `SRS_CHU_KY_02.md` §6 vẫn liệt kê model production là việc chờ chủ dự án.

Mức chắc khác nhau theo nhiệm vụ (§5.2). Bóc yêu cầu báo giá và sinh workflow n8n có khác biệt lớn một chiều trên bộ do team viết. Diễn giải kết quả và vòng agentic chưa đủ bằng chứng để chọn: 27 và 19 câu, p lần lượt 0,34 và 1,0. Chưa có phép đo sau các thay đổi mã từ 29/10 và chưa có phép đo trên câu thật của khách. Việc cần làm: BR-33 đo lại, rồi chủ dự án xác nhận.

### 8.3. Body

- Body chưa trả lời [Body#28](https://github.com/ANSER-Logistics/ANSER-logistics-body/issues/28), đề xuất Body gửi kèm `history` trong mỗi lời gọi `/chat`. Phía Brain chưa có mã BR cho việc nhận `history`; cần thêm khi Body trả lời.
- Body#23: Body có sẵn đường lấy dòng bán cho giao diện của họ, nhưng chưa có bảng chi phí, nên báo cáo lợi nhuận chưa đủ. Body#24 là lược đồ logistics (nhà xe, tuyến, giá cước), không phải nguồn cho `/tools/report`.
- PR #22 bên Body (sửa hiển thị 0% thành "chưa đo được") chờ Body áp bản sửa đã dán trong bình luận của PR đó.

### 8.4. Team

Thành rebase PR #25 và nhánh `feat/14-vllm-vision-client` lên nhánh tính năng. Ngày 15/11 lịch sử git của repo bị viết lại (lý do và cách đồng bộ clone: issue #63), nên clone cũ không còn khớp.

## 9. Quyết định đã chốt

| Ngày | Quyết định | Phương án đã loại | Lý do |
|---|---|---|---|
| 07/11 | `main` là nhánh production; agent không tự gộp vào `main` | Coi `main` là nhánh tích hợp, gộp khi CI xanh | CI xanh cho biết các hành vi đã khoá bằng test không đổi; chủ dự án quyết khi nào bản đạt bảy mục "xong" ở `AGENTS.md` §7 và qua một lần chạy thật |
| 07/11 | Giao việc qua bảng org, nhận kết quả qua PR | Giao qua chat hoặc file markdown | Qua bảng org, ai cũng thấy việc đang ở đâu; qua PR, team `brain` có một chỗ đọc thay đổi |
| 04/11 | `/tools` trả 422 với trường lạ | Bỏ qua trường lạ (hành vi cũ) | Một trường bị bỏ im lặng làm sai báo giá (BR-01) |
| 12/11 | Chu kỳ 02 chạy song song sổ sách và vận tải | Chỉ một mảng: ROADMAP ưu tiên sổ sách, AGENTS ưu tiên vận tải | Mỗi tài liệu đúng ở thời điểm viết, nên không bên nào thắng |
| 12/11 | Lịch sử chat: Body gửi kèm `history`, Brain không lưu | Body thêm bảng chat (cần Body đổi, chưa ai nhận); Brain dùng DB riêng (thêm một thứ phải vận hành, R3) | Nhất quán với R4 |
| 12/11 | "Hôm nay" là ngày giờ Việt Nam, UTC+7 | Dùng UTC | UTC lệch một ngày trong 7 giờ đầu ngày. Body PR #33 cũng chọn UTC+7; Việt Nam không có giờ mùa hè |
| 12/11 | Giá dầu từ 2 ngày tuổi thì cảnh báo, từ 7 ngày thì từ chối (chỉ khi giá dầu được dùng); đổi bằng `FUEL_PRICE_WARN_DAYS` và `FUEL_PRICE_MAX_DAYS` | Chỉ cảnh báo, không có ngưỡng từ chối; ngưỡng 1 và 3 ngày (đề xuất đầu tiên) | "Hôm nay 25 nghìn, ngày mai 30 nghìn": báo giá dựa trên giá cũ là báo giá sai |
| 12/11 | Ngày trong Google Sheet chỉ nhận `YYYY-MM-DD` | Đoán `DD/MM` hay `MM/DD` | `05/11` là 5 tháng 11 hay 11 tháng 5 tuỳ locale; đoán sai thì dùng giá hết hạn |
| 12/11 | p95: cửa sổ 200 lượt, tối thiểu 30 mẫu | Tính trên mọi lượt, không ngưỡng mẫu | Dưới 30 mẫu thì một lượt chậm đủ làm đổi kết luận |
| 15/11 | Mỗi sản phẩm một repo tài liệu: tài liệu của Brain gắn với khách pilot ở repo private `anser-brain-docs`, Body có repo tài liệu riêng | Một repo tài liệu chung cho hai đội (đề xuất ở issue #62) | Chủ dự án chỉ đạo trong phiên làm việc ngày 15/11; hai đội, hai bộ nghiệp vụ |

## 10. Tài liệu cũ lệch mã

Chưa có ai sửa ba tài liệu dưới đây; BR-21 chờ việc sửa. Ai đọc chúng cần biết các chỗ sai sau:

| Tài liệu | Viết ngày | Sai ở |
|---|---|---|
| `SO_TAY_NGUOI_MOI.md` | 22/10 | Ví dụ `curl` của `/tools/vat` dùng `unit_price` và `vat_rate` nên trả 422; ghi 1041 test qua; tên repo Brain là `PCBoiz/ANSER_AI_Logistics` (đúng: `ANSER-Logistics/ANSER_AI_Logistics`); coi `main` là nhánh cũ "đừng gộp"; còn dặn đồng bộ ba bản chép tay của danh mục node n8n |
| `ARCHITECTURE.md` | 27/07 | Danh sách công cụ liệt kê tên không tồn tại (`create_quote`, `send_quote_email`...); module không có thật (`researcher.py`, `integrations.py`); embedder ghi MiniLM ở hai chỗ trong khi mã dùng `bge-m3` (và chính file này ghi `bge-m3` ở §5.1) |
| `ROADMAP.md` | 13/08 | Ghi mảng vận tải "tạm gác" và Redis, vision qua HTTP là "không làm"; kết luận dùng model gốc dựa trên phép đo 15/08 đã lỗi thời (§8.2); bảng điểm chặn ghi "đang mở tạm qua Cloudflare tunnel từ máy dựng" trong khi mục GĐ B của chính file ghi "đưa lên chỗ khách truy cập được: chưa", và tunnel trong compose chưa từng chạy |

`docs/chu-ky-01/` là tài liệu lịch sử, giữ nguyên có chủ ý. Đối chiếu với `AGENTS.md` trước khi làm theo một chỉ dẫn vận hành trong đó.

## 11. Cổng ra của chu kỳ 02

Chu kỳ 02 kết thúc khi:

1. BR-08 và BR-09 đã gộp (Redis và client vision), và compose chạy được một lần thật trên máy thuê.
2. Bốn việc P0 (BR-23 đến BR-26) cùng BR-29, BR-30 và BR-34 đã gộp, mỗi việc có test đỏ trên mã cũ.
3. BR-33 có kết quả đo và chủ dự án chốt model.
4. Ba tài liệu ở §10 đã sửa và `pytest tests/test_tai_lieu_khop_ma.py` xanh.
5. `python offline_training/doi_chieu_hop_dong_body.py` thoát 0 ngay trước khi gộp vào `main`.
6. Chủ dự án quyết thời điểm gộp `main`.

## 12. Thuật ngữ

| Từ | Nghĩa |
|---|---|
| Body | Ứng dụng nghiệp vụ của dự án, repo riêng. Gọi Brain qua HTTP |
| Chủ dự án | Người quyết cuối của dự án ANSER |
| Chu kỳ | Một đợt làm việc có SRS riêng: chu kỳ 01 (26/10 đến 06/11), chu kỳ 02 (từ 12/11) |
| BR-xx | Mã một yêu cầu; BR-01 đến BR-21 nằm trong các SRS chu kỳ trước (`SRS_CHU_KY_01.md` §1.3), BR-22 trở đi nằm ở §6.3 |
| P0, P1, P2 | Mức ưu tiên của một yêu cầu. P0: không xong thì cổng ra chu kỳ không mở. P1: cần cho chu kỳ, trượt thì vẫn mở được cổng kèm ghi chú. P2: làm nếu còn thời gian, trượt thì đẩy sang chu kỳ sau (theo `SRS_CHU_KY_01.md` §1.3) |
| Nguyên tắc "code tính, model nói" | Tên trong `ARCHITECTURE.md`: P1. Tài liệu này không dùng tên đó để khỏi trùng mức ưu tiên P1 |
| R1 đến R5 | Năm ràng buộc ở §2.2 |
| Pilot | Giai đoạn chạy thử với một khách thật trước khi bán rộng |
| Workflow, node | Workflow là một quy trình tự động dạng sơ đồ; node là một bước trong sơ đồ đó |
| n8n | Công cụ chạy workflow |
| Model gốc, bản fine-tune | Model gốc là Qwen3-8B bản AWQ chính thức; bản fine-tune là cùng model huấn luyện thêm bằng dữ liệu của dự án (`anser-v3`) |
| Agentic | Chế độ model và công cụ thay phiên nhau: model điền tham số, mã chạy công cụ, model đọc kết quả |
| Kho tri thức, RAG | Kho tài liệu của khách; RAG là tra kho rồi để model trả lời từ đoạn tìm được |
| Embedder, xếp hạng lại | Embedder biến câu thành vector để so độ giống; xếp hạng lại sắp các đoạn tìm được theo độ liên quan |
| Chroma, BM25 | Chroma lưu vector; BM25 tìm theo từ khoá |
| Recall, MRR | Recall: tỷ lệ tài liệu đúng được tìm thấy. MRR: trung bình nghịch đảo thứ hạng của kết quả đúng đầu tiên |
| Soát sổ | Đối chiếu số liệu sổ sách để tìm sai lệch |
| GTGT | Giá trị gia tăng (thuế) |
| MISA | Phần mềm kế toán khách pilot dùng; Brain đọc file `.xlsx` nó xuất ra |
| MCP | Giao thức để model gọi công cụ; Brain bọc cùng bộ công cụ HTTP theo giao thức này |
| vLLM | Máy chủ chạy model ngôn ngữ; Brain gọi nó qua HTTP khi có `VLLM_BASE_URL` |
| Colab | Dịch vụ Google chạy mã trên GPU thuê theo phiên; dùng để đo, không dùng làm production |
| PR, CI, rebase | PR: đề nghị gộp thay đổi vào một nhánh. CI: chạy test tự động trên mỗi PR. Rebase: đặt các commit của nhánh mình lên đầu nhánh gốc mới |
| Org | Tổ chức GitHub `ANSER-Logistics` |
| Nhánh tính năng, `main` | Nhánh tính năng (`feat/workflow-format-and-deterministic-core`) là nơi cả team làm việc; `main` là nhánh production, chỉ chủ dự án quyết thời điểm gộp |
| Chặn nhầm | Bộ lọc hoặc bộ kiểm chặn một câu đúng. Trong `AGENTS.md` và các tài liệu cũ gọi là "chặn oan" |
| p, khoảng Wilson | p: xem §5.2. Khoảng Wilson 95%: khoảng chứa tỷ lệ thật với độ tin cậy 95%, tính từ một mẫu |
| Chốt suy biến | Bước ở production thay câu trả lời bằng câu an toàn khi model sinh chữ Hán hoặc lặp một cụm tới trần token |

## Phụ lục A. Biến môi trường code đọc

Đếm bằng `grep` trên `src/` ngày 15/11/2026 (29 biến) cộng các biến đọc qua hàm riêng. Nguồn sự thật cho giá trị mặc định là `deploy/.env.example` và `src/core/config.py`; bảng này chỉ để biết có những biến nào. BR-18 theo dõi các biến chưa có trong `.env.example`.

| Nhóm | Biến |
|---|---|
| Chung | `ENV`, `API_AUTH_TOKEN`, `DATABASE_URL`, `ALLOWED_ORIGINS`, `LOG_LEVEL`, `RUNTIME_PROFILE`, `MAX_UPLOAD_BYTES` |
| Model | `TEXT_MODEL_ID`, `VISION_MODEL_ID`, `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`, `TEXT_GPU_FRACTION`, `TEXT_MAX_MODEL_LEN`, `TEXT_QUANTIZATION`, `TEXT_DTYPE`, `TEXT_REPETITION_PENALTY` |
| Kho tri thức | `KB_WORKSPACE_ID`, `KB_EMBEDDER_ID`, `KB_RERANKER_ID`, `KB_DEVICE`, `KB_RELEVANCE_THRESHOLD` |
| Hội thoại | `MAX_HISTORY_TURNS`, `MAX_HISTORY_CHARS` |
| n8n và Body | `N8N_TEMPLATES_DIR`, `N8N_QUOTE_WEBHOOK_URL`, `BODY_CALLBACK_URL` |
| Metrics | `AI_METRICS_PATH`, `AI_METRICS_LOG_CONTENT` |
| Đọc qua hàm riêng (`grep` mẫu không thấy) | `FUEL_PRICE_WARN_DAYS`, `FUEL_PRICE_MAX_DAYS`, `P95_NGUONG_MS`, `P95_MS_MOI_TOKEN`, và nhóm `ANSER_TEXT_*`, `ANSER_VISION_*` (`MAX_CONCURRENT`, `MAX_QUEUE`, `WAIT_TIMEOUT_S`) trong `serving.py` |

## Phụ lục B. Con số trong tài liệu và lệnh sinh ra chúng

Con số nào lệch với kết quả lệnh dưới đây thì tài liệu này sai và cần sửa. Chạy lại từ gốc repo.

| Con số | Lệnh |
|---|---|
| 1663 ca qua, 2 bỏ qua | `ENV=LOCAL python -m pytest tests/ -q -p no:randomly` |
| 68 file test, 1168 hàm test | `ls tests/test_*.py \| wc -l`; `grep -rE "^\s*(async )?def test_" tests --include=test_*.py \| wc -l` |
| CI ít hơn khoảng 28 ca | `gh run list --branch feat/workflow-format-and-deterministic-core --limit 1`, rồi `gh run view <id> --log` và lọc dòng `passed` |
| 193 commit | `git fetch origin && git rev-list --count origin/main..origin/feat/workflow-format-and-deterministic-core` |
| 29 mục route, 25 route nghiệp vụ | `ENV=LOCAL python -c "from src.api.main import app; print(len(app.routes))"` |
| Ba route tự sinh không kiểm token | đặt `API_AUTH_TOKEN`, dùng `fastapi.testclient.TestClient` gọi `/openapi.json`, `/docs`, `/redoc`, `/tools` |
| 36 module, 5 file agents, 32 mẫu n8n | `ls src/core/*.py \| wc -l`; `ls src/agents/*.py \| wc -l`; `ls data/n8n_templates/*.json \| wc -l` |
| 14 gói chưa ghim | `python -c "import tests.test_phu_thuoc as t; print(len(t.CHUA_GHIM))"` |
| Ví dụ của BR-23 | `narration_numbers_ok("Lãi ròng 5.000.000 đồng", '{"net_profit": -5000000}')` và `narration_numbers_ok("Doanh thu đạt 45 triệu đồng", '{"revenue": 120000000}')` (module `src.core.grounding`); trả `(True, None)` khi lỗ hở còn |
| Ví dụ của BR-26 | `loc_truy_van_web("công ty minh long có bắt buộc xuất hoá đơn điện tử không")` (module `src.core.retrieval_policy`); trả lại nguyên câu khi lỗ hở còn |
| `REDIS_URL`, `VLLM_VISION_BASE_URL` không có trong `src/` | `grep -rn "REDIS_URL\|VLLM_VISION_BASE_URL" src --include=*.py` |
| McNemar chính xác | `p = min(1, 2 * sum(C(n, i) for i in 0..min(b, c)) / 2**n)` với `n = b + c`; ví dụ (3 sửa, 7 hỏng) cho 0,344 |
| Khoảng Wilson 95% | `p = k/n`, `z = 1,96`: `(p + z²/2n ± z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n)`; ví dụ 21/27 cho 59,2% đến 89,4% |
| 5,31 GB xuống 0,43 GB | Chép từ mô tả PR #57 (`pip --dry-run`); repo không có lệnh tái hiện |
| Số liệu đo model ở §5.2 | Chép từ `docs/chu-ky-01/BAO_CAO_BR05.md` §6d; chỉ chạy lại được bằng `offline_training/benchmark_v3.py` trên Colab (BR-33) |

## Phụ lục C. Nhật ký dùng AI

| Ngày | Ai | Việc | Cách kiểm | Người duyệt |
|---|---|---|---|---|
| 15/11/2026 | Agent AI (Claude) | Soạn bản đầu từ mã nguồn và tài liệu có sẵn; đo các con số ở Phụ lục B bằng lệnh | Ba reviewer độc lập (cũng là agent AI): đọc lạnh không xem mã; kiểm từng khẳng định với mã và trạng thái GitHub; biên tập văn phong. Kết quả: sửa các số đo model (dùng phiên 29/10 thay phiên 15/08), thêm BR-34, đổi cách đặt tên T/P, thêm định nghĩa cho 20 thuật ngữ | Chưa có |
