# docs/ — tài liệu dự án

Gom lại ngày 04/11/2026. Trước đó 22 file `.md` nằm thẳng ở gốc repo, phần lớn
chồng nội dung nhau, và không có cách nào nhìn ra file nào còn hiệu lực.

## Còn ở gốc repo, có lý do

| File | Vì sao không gom |
|---|---|
| [`AGENTS.md`](../AGENTS.md) | File chỉ thị cho agent. Công cụ đọc nó ở gốc. |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Nguồn sự thật về kiến trúc. `AGENTS.md` trỏ thẳng vào. |
| [`SO_TAY_NGUOI_MOI.md`](../SO_TAY_NGUOI_MOI.md) | Sổ tay người mới. Đọc đầu tiên thì phải thấy đầu tiên. |
| [`ROADMAP.md`](../ROADMAP.md) | Quy ước chung. |

## Gom vào đâu

### [`ky-thuat/`](ky-thuat/) — thiết kế và đo đạc

| File | Nội dung |
|---|---|
| [`TIEN_TRINH_BRAIN.md`](ky-thuat/TIEN_TRINH_BRAIN.md) | Nhật ký tiến trình Brain |
| [`ARCHITECTURE_DIAGRAMS.md`](ky-thuat/ARCHITECTURE_DIAGRAMS.md) | Sơ đồ kiến trúc dạng chữ |
| [`RAG_VLM_KE_HOACH.md`](ky-thuat/RAG_VLM_KE_HOACH.md) | Kế hoạch RAG + vision, ngân sách VRAM |
| [`PHIEN_DO_COLAB.md`](ky-thuat/PHIEN_DO_COLAB.md) | Kết quả các phiên đo trên Colab |
| [`CHAY_THU_NOI_BO.md`](ky-thuat/CHAY_THU_NOI_BO.md) | Quy trình chạy thử nội bộ |

### [`chu-ky-01/`](chu-ky-01/) — chu kỳ 26/10 → 06/11

| File | Nội dung |
|---|---|
| [`SRS_CHU_KY_01.md`](chu-ky-01/SRS_CHU_KY_01.md) | Đặc tả yêu cầu BR-01..BR-07 |
| [`PHAN_VIEC_CHU_KY_01.md`](chu-ky-01/PHAN_VIEC_CHU_KY_01.md) | Phân việc Brain ↔ Body |
| [`GIAO_VIEC_BRAIN.md`](chu-ky-01/GIAO_VIEC_BRAIN.md) | Hồ sơ bàn giao cho người tiếp quản Brain |
| [`BIEN_BAN_CHU_KY_01.md`](chu-ky-01/BIEN_BAN_CHU_KY_01.md) | Biên bản nghiệm thu |
| [`BAO_CAO_BR04.md`](chu-ky-01/BAO_CAO_BR04.md) · [`BAO_CAO_BR05.md`](chu-ky-01/BAO_CAO_BR05.md) | Báo cáo từng hạng mục |

> Đây là **tài liệu lịch sử**. Chúng còn ghi tên repo cũ (`ANSER_AI`,
> `ANSER-v2`) và vài chỉ dẫn sau này đã chứng minh là sai. Cố ý giữ nguyên:
> sửa một biên bản đã ký là viết lại cái đã xảy ra. Chỗ nào chỉ dẫn đã bị đảo
> thì có ghi chú tại chỗ, không sửa lặng lẽ.

### Tài liệu khách hàng — đã chuyển sang repo private `anser-docs`

Từ 15/11/2026 các file dưới đây **không còn trong repo này** (repo công khai): chúng nằm ở
`ANSER-Logistics/anser-docs` (private, chỉ thành viên org đọc được) cùng lịch sử commit.
Đừng thêm lại tài liệu mang tên khách, mã số thuế hay số liệu sổ sách của khách vào repo
công khai (AGENTS.md R2). Các tên file giữ lại ở đây chỉ để biết tìm ở đâu.

| File | Nội dung |
|---|---|
| `GD0_LAM_VIEC_VOI_KHACH.md` | Quy trình giai đoạn 0 |
| `BAN_GIAO_VAN_TAI.md` | Bàn giao nghiệp vụ vận tải |
| `HOANG_PHAT_DU_LIEU_CAN_XIN.md` | Dữ liệu cần xin từ khách |
| `HOANG_PHAT_SOAT_SO_1108.md` | Kết quả soát sổ |
| `HOANG_PHAT_DANH_GIA_SAN_PHAM.md` | Đánh giá sản phẩm |
| `HOANG_PHAT_GUI_KHACH.md` | Bản soạn gửi khách |

### Ở ngay `docs/`

| File | Nội dung |
|---|---|
| [`GITHUB_ORG_DE_XUAT.md`](GITHUB_ORG_DE_XUAT.md) | Đề xuất lập GitHub Organization + hướng dẫn từng bước |
| [`kien-truc-anser.drawio`](kien-truc-anser.drawio) | Sơ đồ kiến trúc, sửa tay được (draw.io) |
| [`hinh/`](hinh/) | SVG viết tay dùng trong tài liệu |
| [`ban-in/`](ban-in/) | Bản in PDF/HTML — **sinh ra**, đừng sửa trực tiếp |
| [`lora-14b-da-bo/`](lora-14b-da-bo/) | Cấu hình LoRA của nhánh 14B đã bỏ |

## Link cũ bị gãy

GitHub **không** chuyển hướng file đã di chuyển. Link trỏ vào `.../blob/main/TEN_FILE.md`
từ trước 04/11/2026 sẽ ra 404 — tra bảng trên để biết đường dẫn mới. Lịch sử git
vẫn liền mạch (`git mv`), nên `git log --follow <đường dẫn mới>` xem được đầy đủ.

## Đã xoá

| File | Khi | Lấy lại |
|---|---|---|
| `offline_training/db_schema.txt` | 04/11/2026 | `git show f77096c:offline_training/db_schema.txt` |
| `_backups/` (226MB) | 03/11/2026 | ba bản sao giống hệt nhau; mọi thứ có trong git, trừ [`lora-14b-da-bo/`](lora-14b-da-bo/) đã giữ lại |
| `src/archive/` | 05/08/2026 | `git show 306a16c:src/archive/<file>` |
