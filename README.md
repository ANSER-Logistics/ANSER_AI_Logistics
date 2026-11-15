# ANSER Brain

Dịch vụ FastAPI cung cấp năng lực AI cho nền tảng ANSER: trả lời câu hỏi nghiệp vụ, đọc hoá đơn, soát sổ, báo giá vận tải. Phần tính tiền và đối soát là mã Python thuần có test; model ngôn ngữ chỉ diễn giải kết quả. ANSER Body (repo riêng) là ứng dụng nghiệp vụ gọi Brain qua HTTP.

## Tài liệu

Toàn bộ tài liệu (kiến trúc, SRS, sổ tay người mới, roadmap) nằm ở repo **private**
[`ANSER-Logistics/anser-brain-docs`](https://github.com/ANSER-Logistics/anser-brain-docs); chỉ thành viên org đọc được.
Thành viên mới đọc [`docs/SRS_BRAIN.md`](https://github.com/ANSER-Logistics/anser-brain-docs/blob/main/docs/SRS_BRAIN.md) trước.

Ở lại repo này:

| File | Nội dung |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Chỉ thị vận hành: năm ràng buộc bất biến (R1 đến R5), quy trình làm việc, định nghĩa "xong". Đọc trước khi sửa mã |
| `README.md` trong `src/`, `deploy/`, `workflows/logistics/`, `offline_training/`, `data/` | Mô tả mã nằm cạnh mã |

## Chạy thử không cần GPU

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -c requirements.txt fastapi httpx pydantic numpy json_repair sqlalchemy requests ddgs python-multipart openpyxl
ENV=LOCAL python -m pytest -q                        # Windows PowerShell: $env:ENV="LOCAL"
ENV=LOCAL uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

`ENV=LOCAL` không nạp model thật: toàn bộ lớp tất định, bộ định tuyến và API chạy và test được trên CPU. Các giá trị `ENV` khác và biến cấu hình phần cứng: AGENTS.md mục R5.

## Đóng góp

Giao việc qua project của org, trả việc bằng Pull Request vào nhánh tính năng; `main` là production và chỉ chủ dự án quyết thời điểm gộp (AGENTS.md §5.0, §6.0). PR đổi route, module `src/core/`, biến môi trường hay hành vi mà tài liệu mô tả thì nêu rõ trong mô tả PR và mở PR sửa tài liệu ở repo `anser-brain-docs` (AGENTS.md §4.2).
