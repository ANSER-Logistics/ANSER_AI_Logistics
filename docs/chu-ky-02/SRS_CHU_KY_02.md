# SRS — Đặc tả yêu cầu, Brain, chu kỳ 02

**Lập ngày:** 12/11/2026 · **Mốc mã nguồn:** `feat/workflow-format-and-deterministic-core` @ `2f0df13`
**Phạm vi:** chỉ repo Brain (`ANSER-Logistics/ANSER_AI_Logistics`). Việc cần Body đổi chỉ được *đề xuất bằng văn bản* (AGENTS §1)
**Chu kỳ:** **chưa chốt ngày.** Đề nghị hai tuần, bắt đầu khi chủ dự án chốt. Tài liệu này **không đặt hạn theo ngày** — chỉ đặt thứ tự (cột *Làm sau*), vì hạn là quyết định của chủ dự án
**Trạng thái:** bản thảo, chờ chủ dự án duyệt §6

Khuôn theo [SRS chu kỳ 01 §1.2](../chu-ky-01/SRS_CHU_KY_01.md): mỗi yêu cầu có *Vì sao*, *Yêu cầu* (PHẢI / NÊN / CÓ THỂ), *Nghiệm thu* (lệnh chạy được) và *Ngoài yêu cầu*. Yêu cầu nào không kiểm được bằng lệnh thì nó chưa phải yêu cầu.

---

## 1. Hướng của chu kỳ

Chủ dự án chốt ngày 12/11/2026: **chạy song song hai nghiệp vụ.**

| Nghiệp vụ | Trạng thái |
|---|---|
| **Sổ sách / kế toán** | Phần đã chạy trên dữ liệu thật của khách pilot (ROADMAP GĐ A). Chu kỳ này: bịt các chỗ "chưa biết" bị đổi thành 0, thêm test cho các hàm tính giá vốn và nạp danh mục |
| **Logistics / báo giá vận tải** | Code và test có sẵn nhưng chưa hiệu chỉnh trên số của ai (ROADMAP: "tạm gác" ngày 13/08). Chu kỳ này: sửa các lỗi *sai im lặng* đã đo được, **không** phát triển thêm |

Hai tài liệu từng nói ngược nhau (ROADMAP 13/08 "tạm gác" so với AGENTS §8 "ưu tiên 1"). AGENTS §8 đã sửa theo quyết định này.

**Hạ tầng (S2)** là trục thứ ba, và là chỗ sản phẩm còn nợ nhiều nhất: Redis, vision qua HTTP, tunnel, và một `docker-compose.yml` mà chính nó ghi *"CHƯA TỪNG ĐƯỢC CHẠY"*.

### 1.1. Ai làm gì

| Người | Trục | Việc |
|---|---|---|
| **Trần Thành** (`tranthanh-riu`) | Hạ tầng + AI | BR-06, BR-08, BR-09, BR-10, BR-11, BR-12 |
| **Dương Sơn** (`Dgsonn`) | Kiểm thử tất định (người mới với AI — mỗi issue có phần giải thích nghiệp vụ) | BR-13 đến BR-18 |
| **Agent Brain** (`PCBoiz`) | Sửa lỗi R1/R2 trong mã, tài liệu, sổ quyết định | §2 (đã làm) và BR-19, BR-20 |
| **Phạm Thế Minh** (`wikiepeidia`) | Chưa giao — đang làm bên Body, chỉ có quyền đọc repo này | — |

Mọi việc giao qua [bảng org số 6](https://github.com/orgs/ANSER-Logistics/projects/6), trả bằng PR vào `feat/workflow-format-and-deterministic-core` cho team `brain` duyệt (AGENTS §5.0). **Không PR nào vào `main`** (§6.0).

### 1.2. Luật tránh giẫm chân nhau

Chu kỳ 01 ghi nhận một lỗi điều phối: bốn việc giao cùng lúc cùng chạm `requirements.txt`, hai PR bị xung đột. Từ chu kỳ này **mỗi issue ghi sẵn nó sẽ chạm file nào và phải làm sau việc nào**. Bảng phụ thuộc ở §4 là bản tổng hợp; file trùng nhau thì làm **tuần tự**, không song song.

---

## 2. Đã làm trong ngày 12/11/2026 (agent, tự gộp khi CI xanh)

Năm PR vào nhánh tính năng, mỗi PR có test **đỏ trên mã cũ**.

| PR | Lỗi đã đóng |
|---|---|
| [#32](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/32) | Mọi tool agentic và `/mcp/tools/call` trả `Unauthorized` khi bật `API_AUTH_TOKEN` (compose bắt buộc đặt). Vòng agentic không còn nhận câu kết luận khi còn kế hoạch tool |
| [#33](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/33) | Chốt số liệu đọc `12500000.0` thành `125000000` (gấp mười); bộ lọc truy vấn web để lọt số tiền gõ không dấu / bằng chữ (R2) |
| [#40](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/40) | "Chưa biết" bị đổi thành 0 ở công nợ, báo cáo lãi lỗ, doanh số, nháp báo giá |
| [#41](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/41) | Workflow n8n báo giá không xét tuyến (tính giá tuyến này bằng giá tuyến khác); báo giá không ghi giá và thời điểm đầu vào |
| [#42](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/42) | Ba công cụ báo "sạch" khi chưa làm gì (`soat_hinh_dang_tra_ve`, `merge_all`, thiếu `.dockerignore`); xoá `update_price` chết |

**Mốc đo sau PR #42:** local `1463 passed, 2 skipped`; CI `1435 passed, 6 skipped` (CI thấp hơn vì thiếu `python-docx`/`pypdf` — BR-15). ruff và mypy 83 file sạch.

---

## 3. Yêu cầu chức năng

### BR-08. Trạng thái tác vụ nền dùng chung qua Redis
**Ưu tiên** P0 · **Người làm** Thành · **Làm sau** không · **Issue** [#15](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/15), [PR #25](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/25) (code đã xong, cần rebase)

**Vì sao.** `TASK_REGISTRY` là dict trong RAM: worker A ghi, worker B hỏi → "Task not found"; restart mất hết. Brain buộc phải chạy `--workers 1`.

**Yêu cầu.**
1. PHẢI: có `REDIS_URL` thì mọi worker dùng chung Redis; không có thì dùng RAM như cũ (`ENV=LOCAL` không cần Redis).
2. PHẢI: Redis lỗi thì lùi về RAM cho lời gọi đó, ghi log lỗi, `/health` báo `degraded`. `/chat` không sập.
3. PHẢI: task tự xoá sau 24 giờ (`TASK_TTL_S`); giữ trường `_owner`.

**Nghiệm thu.** `ENV=LOCAL pytest tests/test_task_registry_redis.py -q -p no:randomly`, trong đó có ca *hai tiến trình khác nhau thấy cùng một task*.

**Ngoài yêu cầu.** Không nâng `--workers` mặc định trong compose; chỉ nâng được khi `/health` báo `task_registry.backend: "redis"`.

### BR-09. Client HTTP cho `vllm-vision`
**Ưu tiên** P0 · **Người làm** Thành · **Làm sau** BR-08 · **Issue** [#14](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/14) (nhánh `feat/14-vllm-vision-client` đã có, chưa mở PR)

**Vì sao.** Compose dựng container vision nhưng không code nào gọi tới nó; ở `ENV=SERVER` mọi lời gọi ảnh ném `BackendUnavailable`, nên `/ocr` và `/ocr/freight` không chạy được ở đích triển khai.

**Yêu cầu.**
1. PHẢI: `/health` ở `ENV=SERVER` có `vision_backend` khác `"none"`.
2. PHẢI: có test gọi server giả trên socket thật.
3. PHẢI: đường vision giữ số token như đường text (`KetQuaSinh`, PR #23) **hoặc** ghi `None` có chủ ý. `vision()` hiện trả `str` và vứt `usage` — đúng lỗi #23 vừa sửa cho đường text.
4. PHẢI KHÔNG: đi vòng qua lớp sanitize đầu ra VLM (BR-19).

**Nghiệm thu.** `ENV=LOCAL pytest tests/test_vision_server.py tests/test_engine_backend.py -q -p no:randomly`; `CHUA_NOI` trong `tests/test_deploy_config.py` không còn hai biến vision.

**Ngoài yêu cầu.** Không đo độ chính xác đọc hoá đơn (chưa có hoá đơn thật — ROADMAP ghi VLM "🔴 chưa đo").

### BR-10. Nối ngưỡng p95 vào `/health`
**Ưu tiên** P1 · **Người làm** Thành · **Làm sau** BR-08, BR-09 · **Issue** [#9](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/9)

**Vì sao.** Hệ thống ghi số token và tính được p95 nhưng không kết luận gì; chu kỳ 01 ghi p95 là "ngưỡng chốt" mà chưa nối vào đâu.

**Yêu cầu.** (đã chốt 12/11/2026)
1. PHẢI: chỉ `ms/token` được hạ `degraded`.
2. PHẢI: tính trên **cửa sổ 200 lượt gần nhất**, và **tối thiểu 30 mẫu** mới kết luận; dưới 30 thì `/health` nói *"chưa đủ mẫu"*, không báo xanh.
3. PHẢI: lượt có `completion_tokens` là `None` **không** vào mẫu (không coi là 0, không bỏ qua im lặng).
4. NÊN: cô lập `AI_METRICS_PATH` trong `tests/conftest.py` — test hiện ghi lẫn vào file metrics thật.

**Nghiệm thu.** `ENV=LOCAL pytest tests/test_deploy_config.py -q -p no:randomly` và một test mới cho cả ba ca (dưới 30 mẫu, trên ngưỡng, có mẫu `None`).

**Ngoài yêu cầu.** Lưu metrics qua restart (volume hoặc đẩy sang Body) — ghi vào mô tả PR để theo dõi, không làm ở đây.

### BR-06. Bộ đo RAG *(chuyển từ chu kỳ 01)*
**Ưu tiên** P1 · **Người làm** Thành · **Làm sau** không (chỉ file mới) · **Issue** [#34](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/34)

**Vì sao.** `src/core/knowledge.py` có 571 dòng và 70 test đơn vị nhưng **không một chỉ số recall hay faithfulness nào**. ROADMAP ghi RAG "🟡 chưa đo".

**Yêu cầu.**
1. PHẢI: một lệnh in bảng gồm ít nhất **Recall@20** và **MRR** (tầng truy hồi) và một chỉ số tầng sinh.
2. PHẢI: bộ câu hỏi có người rà **20% mẫu**; câu hỏi tự trả lời được không cần truy hồi thì loại.
3. PHẢI KHÔNG: gửi **tài liệu của khách** tới DeepSeek (R2). DeepSeek chỉ cho corpus công khai (nghị định, thông tư); tài liệu khách thì gõ tay hoặc sinh bằng model local.
4. PHẢI: mở rộng `grounding.py` (đã là faithfulness về con số) thành chỉ số báo cáo được, không thay bằng thứ khác.
5. Ngưỡng khởi điểm Recall@20 ≥ 0,8; chưa đạt thì **ghi số thật**, không chỉnh ngưỡng cho vừa.

**Nghiệm thu.** `py offline_training/do_rag.py` ra bảng; số liệu đính vào PR kèm tỷ lệ đã rà và tập nào là công khai / gõ tay.

**Ngoài yêu cầu.** Không đổi embedder/reranker, không đổi `knowledge.py`, không nạp nguồn mới.

### BR-11. Compose nhất quán với phần còn lại của repo
**Ưu tiên** P1 · **Người làm** Thành · **Làm sau** BR-09 · **Issue** [#35](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/35)

**Vì sao.** `docker-compose.yml` ghim `vllm/vllm-openai:v0.8.5` trong khi `requirements.txt` đòi `vllm>=0.10.2,<0.12` và mọi phép đo (BR-04, BR-05) làm trên 0.10.2–0.11.2; hành vi grammar trên 0.8.5 chưa ai đo. Nó còn ép `--quantization=awq` trái với `config.py` (benchmark và serving sẽ chạy hai kernel khác nhau).

**Yêu cầu.** PHẢI đưa image về bản trong khoảng cho phép và ghi bản nào đã được đo; PHẢI bỏ `--quantization` cứng, đọc `TEXT_QUANTIZATION`; PHẢI thêm test ghim hai điều đó vào `tests/test_deploy_config.py` để đổi một bên mà quên bên kia thì CI đỏ.

**Nghiệm thu.** Test mới đỏ trước sửa, xanh sau. Kiểm `docker compose up` + `/health` cần GPU → gộp vào phiên Colab của BR-12.

**Ngoài yêu cầu.** **Không chọn model** (fine-tune hay model gốc) — quyết định của chủ dự án, [#11](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/11) mục D.

### BR-12. Ghim nhóm gói AI
**Ưu tiên** P2 · **Người làm** Thành · **Làm sau** BR-13, cần một phiên Colab có GPU · **Issue** [#13](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/13)

**Vì sao.** `CHUA_GHIM` còn 14 gói; 11 trong số đó là nhóm AI (`torch`, `transformers`, …) mà chỉ GPU thật mới kiểm được bản nào chạy.

**Yêu cầu.** PHẢI ghim trần từng gói đã kiểm, hoặc ghi lý do không ghim (như `pytz`); PHẢI soát mọi chỗ `import openai` (xem AGENTS R2: `src/` không import nó).

**Nghiệm thu.** `pytest tests/test_phu_thuoc.py -q -p no:randomly`; `CHUA_GHIM` rỗng hoặc chỉ còn gói có lý do ghi rõ.

### BR-13. Tách `requirements-gpu.txt`
**Ưu tiên** P1 · **Người làm** Sơn · **Làm sau** không · **Issue** [#17](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/17) (nhánh `chore/17-tach-requirements-gpu` còn nguyên; PR #27 bị GitHub tự đóng — rebase rồi mở PR mới)

**Vì sao.** Đo bằng `pip --dry-run`: image kéo `torch` CUDA và 27 gói NVIDIA — **5,31 GB** wheel tải về; tách ra còn **0,43 GB**.

**Yêu cầu.** PHẢI: `requirements.txt` chỉ còn phần CPU, `requirements-gpu.txt` có phần còn lại; PHẢI: dòng ghim phiên bản của #6 **đi theo gói** sang đúng file; PHẢI KHÔNG: gói nào nằm ở cả hai file với hai ràng buộc khác nhau (R4).

**Nghiệm thu.** `pytest tests/test_phu_thuoc.py -q -p no:randomly`; NÊN thêm test *không gói nào xuất hiện ở cả hai file* (test hiện đọc từng file riêng nên không bắt được).

**Ngoài yêu cầu.** Chưa có số `docker images` thật (daemon chưa chạy trên máy tác giả); ghi rõ là số ước tính.

### BR-14. Gỡ ghim `fastapi<0.137`
**Ưu tiên** P1 · **Người làm** Sơn · **Làm sau** BR-13 · **Issue** [#30](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/30)

**Vì sao.** Ở FastAPI 0.162.2, `include_router` gói route vào `_IncludedRouter`, nên `tests/test_auth_bao_phu.py` quét ra **0 endpoint** và 46 ca kiểm token skip im lặng. Ghim `<0.137` chỉ hoãn vấn đề.

**Yêu cầu.** PHẢI: `moi_endpoint()` đi xuống cả router lồng nhau; PHẢI: số endpoint thấy được bằng nhau ở cả hai bản FastAPI.

**Nghiệm thu.** `pytest -rs` không còn ca *"empty parameter set"*; `requirements.txt` → `fastapi<1`.

### BR-15. CI đỏ khi có ca skip chưa khai báo
**Ưu tiên** P1 · **Người làm** Sơn · **Làm sau** BR-08, BR-13 · **Issue** [#29](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/29)

**Vì sao.** "Test mất đối tượng kiểm mà vẫn báo xanh" đã cắn repo ba lần trong một tuần, và hiện có năm chốt chặn viết tay mỗi chỗ một kiểu. Thêm: CI không cài `python-docx` và `pypdf`, nên khoảng 27 test bị skip theo module mà `pytest -q` không in lý do.

**Yêu cầu.** PHẢI: một cổng chung — so danh sách skip với danh sách đã khai, lệch thì CI đỏ; PHẢI: cài hai gói còn thiếu và **báo cáo test nào đỏ khi lần đầu chạy thật** (không sửa lặng lẽ); NÊN: bỏ bớt chốt chặn lẻ nếu cổng chung đã phủ.

**Nghiệm thu.** Thêm một `pytest.skip` chưa khai vào nhánh phụ → CI đỏ; gỡ ra → xanh.

### BR-16. Test cho các chỗ tính toán chưa có test
**Ưu tiên** P1 · **Người làm** Sơn · **Làm sau** không (chỉ file test mới) · **Issue** [#36](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/36)

**Vì sao.** Đợt soát 12/11 không thấy test nào gọi tên `inventory.unit_cost_of` (kết quả được Body ghi thành giá vốn hàng bán), `/tools/partner-import`, `/tools/product-import`.

**Yêu cầu.** PHẢI: tự kiểm lại ba lệnh `grep` trước (phép đo tự động là giả thuyết); PHẢI: mỗi cách tính một ca có đáp án tính tay, một ca thiếu dữ liệu (ra `None`, không phải `0`); PHẢI: mỗi endpoint kiểm 200, **401 không token**, và file hỏng → lỗi có cấu trúc chứ không phải 500; PHẢI KHÔNG: sửa code Brain trong PR này — gặp bug thì ghi vào issue.

**Nghiệm thu.** `pytest tests/test_unit_cost_of.py tests/test_import_endpoints.py -q -p no:randomly`; mỗi test chứng minh được là có thể đỏ.

### BR-17. `carrier_selection`: không để giá chào sau ghi đè giá chào trước
**Ưu tiên** P1 · **Người làm** Sơn · **Làm sau** không (PR #41 đã gộp) · **Issue** [#37](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/37)

**Vì sao.** `carrier_selection.py:293` dựng `{o.carrier_id: o}`; nhà xe có hai giá chào thì giá sau ghi đè giá trước, im lặng. Sau PR #41 n8n đã lọc theo tuyến nên mỗi nhà xe chỉ còn tối đa một giá cho một tuyến — lỗi này chỉ còn khi dữ liệu nguồn **trùng**.

**Yêu cầu.** PHẢI: nhà xe có nhiều hơn một giá chào cho cùng yêu cầu bị đưa vào `rejected` với lý do tiếng Việt rõ ràng, không chọn bừa; PHẢI KHÔNG: tự chọn "giá thấp nhất" hay bất kỳ quy tắc nghiệp vụ nào (việc của chủ dự án).

**Nghiệm thu.** Test mới đỏ trên mã cũ, xanh sau sửa; các test `carrier_selection` hiện có không đổi kết quả.

### BR-18. Soát biến môi trường code đọc mà `.env.example` không ghi
**Ưu tiên** P2 · **Người làm** Sơn · **Làm sau** BR-09 · **Issue** [#38](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/38)

**Vì sao.** Biến không được ghi thì người triển khai không đặt được, và mặc định của code âm thầm quyết định thay họ — tiêu chí R5 *"chuyển máy chỉ đổi `.env`"* không thật. Đo 12/11: ít nhất mười biến (`KB_*`, `LOG_LEVEL`, `MAX_*`, `TEXT_DTYPE`, `TEXT_REPETITION_PENALTY`, `ANSER_VISION_*`); riêng `ANSER_VISION_*` được ghép bằng f-string nên grep tên đầy đủ không ra.

**Yêu cầu.** PHẢI: tự soát lại toàn bộ `os.getenv`/`os.environ` trong `src/`; PHẢI: mặc định ghi vào `.env.example` **đúng** với mặc định trong code; PHẢI KHÔNG: đặt giá trị thật cho biến nào trông giống bí mật (R2b — dừng và hỏi).

**Nghiệm thu.** `pytest tests/test_deploy_config.py -q -p no:randomly`; PR ghi *"đã đối chiếu N biến, thiếu M, đã thêm M"*.

### BR-19. Sanitize đầu ra VLM, và gộp prompt vision về `prompts.py`
**Ưu tiên** P1 · **Người làm** agent · **Làm sau** BR-09 · **Issue** [#39](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/39)

**Vì sao.** AGENTS §4.1 quy tắc 8 đòi sanitize; **lớp này không tồn tại** — chuỗi do model đọc ảnh sinh ra đi thẳng xuống Body. Hoá đơn là thứ người ngoài soạn.

**Yêu cầu.** PHẢI: hàm thuần trong `src/core/` giới hạn độ dài, bỏ ký tự điều khiển, chuẩn hoá NFC, **gắn cờ** (không xoá im lặng) chuỗi trông như chỉ dẫn cho model; PHẢI: áp cho `/ocr`, `/ocr/freight`, `/upload` và trường `raw` ở đường lỗi; PHẢI: chuyển bốn prompt inline trong `vision.py` về `prompts.py`, bỏ ví dụ `"price": 0 … "total": 0` (dạy model điền 0).

**Nghiệm thu.** Test đỏ trên mã cũ cho từng đường; `tests/test_quy_tac_code.py` mở rộng quy tắc 7 cho `src/agents/`.

**Ngoài yêu cầu.** Schema hoá đơn bán lẻ (chờ chủ dự án chốt bán lẻ hay vận tải).

### BR-20. `/health` nói thật khi lịch sử chat không dùng được
**Ưu tiên** P2 · **Người làm** agent · **Làm sau** BR-08, BR-09 (cùng `main.py`) · **Việc** kanzo `brain#216`, liên quan [#19](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/19)

**Vì sao.** Không có `DATABASE_URL` thì `memory.kiem_luoc_do()` cố ý trả `None` cho SQLite, nên `/health` báo khoẻ trong khi lịch sử **không bao giờ** hoạt động. Với DB thật của Body thì `memory_schema_error` ("thiếu 6/6 bảng") làm `/health` `degraded` mãi cho tới khi #19 xong.

**Yêu cầu.** PHẢI: `/health` phân biệt "chưa cấu hình" với "khoẻ"; PHẢI: không phụ thuộc Body#28.

**Nghiệm thu.** Test mới cho cả hai chế độ.

### BR-21. Đi lại sổ tay người mới trên máy sạch
**Ưu tiên** P2 · **Người làm** Sơn · **Làm sau** BR-13 · **Issue** [#18](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/18)

**Vì sao.** Đây là việc **duy nhất không ai khác làm được**: người đã đọc `SO_TAY_NGUOI_MOI.md` quá nhiều lần thì không còn thấy chỗ nó bỏ qua một bước.

**Yêu cầu.** PHẢI: đi từ đầu §2 trên máy sạch và ghi **nguyên văn** mọi chỗ vướng, theo thứ tự gặp. Chưa sửa sổ tay trong issue này.

**Nghiệm thu.** Một bình luận liệt kê đủ mọi chỗ vướng.

---

## 4. Thứ tự và phụ thuộc

```
Thành:  BR-08 (PR #25) ──► BR-09 (#14) ──► BR-10 (#9) ──► BR-11 (#35)      BR-06 (#34): song song, chỉ file mới
                                    │
                                    └──► BR-19 (agent) ──► BR-20 (agent)

Sơn:    BR-13 (#17) ──► BR-14 (#30)                         BR-16 (#36), BR-17 (#37): bắt đầu ngay, song song
                  ├──► BR-15 (#29, cần BR-08)
                  ├──► BR-12 (Thành, cần Colab)
                  └──► BR-21 (#18)        BR-18 (#38) sau BR-09
```

**Cặp xung đột đã đo** (git merge-tree, 12/11): `PR #25` ↔ `#14` cùng sửa `src/api/main.py`, `tests/test_deploy_config.py`, `deploy/README.md`, `ROADMAP.md`; `#17` ↔ `#30` cùng sửa `requirements.txt` và `tests/test_phu_thuoc.py`; `#9` ↔ cả hai việc đầu. Các việc agent làm trong ngày 12/11 **không chạm** file nào của ba PR đang mở.

**File đang cấm sửa** cho tới khi BR-08, BR-09, BR-13 gộp: `ROADMAP.md`, `SO_TAY_NGUOI_MOI.md`, `.github/workflows/ci.yml`, `requirements.txt`, `src/api/main.py`, `src/core/engine.py`, `deploy/*`.

---

## 5. Yêu cầu phi chức năng

| # | Yêu cầu |
|---|---|
| NFR-01 | Mọi PR có test **đỏ trên mã cũ**, và PR ghi lệnh đã chứng minh điều đó |
| NFR-02 | **Chi phí hạ tầng mới: 0đ** (R3). Bất kỳ việc nào cần thuê GPU phải kèm VNĐ/tháng và doanh thu chi trả — hiện chưa có |
| NFR-03 | Không dữ liệu khách rời hệ thống (R2). Không đưa giá trị bảo mật vào env mà chưa hỏi chủ dự án (R2b) |
| NFR-04 | Chạy được ở `ENV=LOCAL` không cần GPU, trừ các ca ghi rõ cần GPU |
| NFR-05 | Mô tả PR có mục **"Hành vi hướng ra khách"** khi đổi cách Brain trả lời; và nói rõ cái gì *chưa chắc* |
| NFR-06 | Mỗi lần gộp: đóng issue và đặt Status trên bảng bằng tay — GitHub không tự đóng vì nhánh đích không phải `main` |

---

## 6. Việc chờ chủ dự án — chặn một phần chu kỳ

Danh sách đầy đủ ở [#11](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/11) (15 mục). Chỗ chúng chặn chu kỳ này:

| Việc | Chặn |
|---|---|
| Gộp [PR #5](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/pull/5) (CODEOWNERS, sửa CI của `main`) | Luật "team `brain` duyệt PR" chưa tự chạy |
| Cấp `DEEPSEEK_API_KEY` | Cổng đo chất lượng mới đo được 1/4 tập; BR-06 không phụ thuộc vì dùng corpus công khai |
| Chọn model chạy production (fine-tune hay model gốc) | BR-11 không được chọn thay chủ dự án; compose đang nạp fine-tune |
| Ngưỡng tuổi giá dầu | Báo giá đã *ghi* tuổi giá dầu (PR #41) nhưng chưa từ chối gì |
| Body trả lời [Body#28](https://github.com/ANSER-Logistics/ANSER-logistics-body/issues/28) | S7 (lịch sử chat) và BR-20 phần còn lại |
| Thuê GPU, chỗ đặt cho khách, ai host n8n | Cổng ra "chạy được trên máy khách truy cập được" |

---

## 7. Cổng ra chu kỳ

Chu kỳ 02 đạt khi đủ cả tám:

- [ ] PR #25 và #14 đã gộp; `/health` ở `ENV=SERVER` báo `task_registry.backend: "redis"` và `vision_backend` khác `"none"` (BR-08, BR-09)
- [ ] `/health` có p95 `ms/token` với cửa sổ 200 / tối thiểu 30 mẫu và có test cho ca *chưa đủ mẫu* (BR-10)
- [ ] Có **bảng chỉ số RAG** (Recall@20, MRR, một chỉ số tầng sinh) với số thật đính vào PR (BR-06)
- [ ] `requirements-gpu.txt` đã tách và không gói nào nằm ở cả hai file (BR-13)
- [ ] CI đỏ khi có skip chưa khai báo, và ~27 test đang skip im lặng đã chạy thật (BR-15)
- [ ] Ba chỗ tính toán chưa có test (`unit_cost_of`, hai endpoint nạp Excel) đã có test; bug nào test tìm ra được **ghi thành issue**, không sửa lặng lẽ (BR-16)
- [ ] Nhà xe có nhiều giá chào cho cùng yêu cầu không còn bị chọn bừa (BR-17)
- [ ] `pytest -q` xanh, `ruff` và `mypy` sạch, đo trên đúng mã đã chạy

Mỗi mục chưa đạt PHẢI có một dòng nêu lý do và người chịu trách nhiệm đẩy tiếp. **Gộp nhánh tính năng vào `main` KHÔNG nằm trong cổng này** — đó là quyết định riêng của chủ dự án theo AGENTS §6.0, và `pytest` xanh không phải tiêu chí.

---

## 8. Ngoài phạm vi chu kỳ 02

| Không làm | Vì sao |
|---|---|
| Hiệu chỉnh công thức báo giá trên số thật | Cần 15–20 báo giá lịch sử của một khách làm vận tải; khách pilot hiện không làm vận tải |
| `reconciliation.py` và `InvoiceFieldValidator` (S5) | Cần dữ liệu sổ kho từ Body (đổi bên Body) |
| Lược đồ logistics bên Body (S6) | Chỉ được đề xuất; đã có Body#23, Body#24, chưa ai trả lời |
| Huấn luyện lại model | Bảng phân loại lỗi (BAO_CAO_BR05) là đầu vào, nhưng chưa có `eval_*` đủ để đo và chưa có quyết định model |
| Bật phân loại số theo hình dạng tiền (`chi_kiem_so_tien`) | Phụ thuộc `eval_narration` và chủ dự án duyệt ([#10](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/10)) |
| Sửa hoặc mở repo Body | AGENTS §1 |

---

## 9. Tham chiếu

[AGENTS.md](../../AGENTS.md) · [SRS chu kỳ 01](../chu-ky-01/SRS_CHU_KY_01.md) · [Biên bản chu kỳ 01](../chu-ky-01/BIEN_BAN_CHU_KY_01.md) (mục 7: việc đẩy sang chu kỳ 02) · [ROADMAP.md](../../ROADMAP.md) · [Bảng việc org](https://github.com/orgs/ANSER-Logistics/projects/6) · [Sổ quyết định #11](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/11)
