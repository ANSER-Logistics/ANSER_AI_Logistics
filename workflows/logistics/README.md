# workflows/logistics — 4 workflow n8n cho khách pilot logistics

Viết tay 27/07/2026 theo đúng mẫu 32 workflow thật của Body (nhánh `dev`).
**Được phép dùng node `code`** vì đây là template người viết — chính sách chặn
`code` chỉ áp cho workflow do AI sinh (ARCHITECTURE.md §11.7).

## Luồng nghiệp vụ tổng

```
Chủ DN nhắn Brain (đang lái xe): "báo giá xe 5 tấn Hữu Nghị đi Hải Phòng…"
  → Brain trích xuất (guided_json) → POST webhook logistics-quote
  → n8n đọc Sheet (Carriers/CarrierQuotes/PricingRules/FuelIndex mới nhất)
  → Brain /tools/carrier-selection → /tools/quote        (tính thuần, P1)
  → nháp lưu QuoteDrafts + embed CÓ BIÊN về Discord chủ DN   ← chỉ nội bộ
  → chủ DN bấm link duyệt → webhook logistics-approve
  → email CHỈ TỪ PHẦN CÔNG KHAI gửi khách cuối (Gmail OAuth của khách) → đánh dấu sent
```

| Workflow | Trigger | Vai trò |
|---|---|---|
| `logistics_fuel_price_sync` | 6h sáng hàng ngày | Cào giá diesel PVOIL → `FuelIndex` (realtime theo AGENTS 3.1c). **Bóc không được thì THROW, không ghi giá bịa** |
| `logistics_quote_request` | webhook `POST /webhook/logistics-quote` | Sheet → `/tools/carrier-selection` → `/tools/quote` → nháp + Discord duyệt |
| `logistics_quote_approve` | webhook `GET /webhook/logistics-approve?draft_id=` | Guard idempotent (bấm 2 lần không gửi 2 email) → Gmail khách cuối → đánh dấu `sent` |
| `logistics_debt_reminder` | thứ 2 hàng tuần 8h | `Receivables` → lọc quá hạn (tất định, **không LLM**) → Discord chủ DN |

## Biến môi trường n8n cần đặt

| Biến | Ý nghĩa |
|---|---|
| `LOGISTICS_SHEET_ID` | ID Google Sheet dựng từ [`data/sheet_templates/`](../../data/sheet_templates/) |
| `BRAIN_BASE_URL` | URL Brain (FastAPI) — nơi có `/tools/*` |
| `ANSER_API_TOKEN` | Token cho header `X-API-Token` |
| `DISCORD_WEBHOOK_URL` | Kênh chủ DN duyệt/nhận cảnh báo (pilot; sau chuyển Zalo = đổi biến này) |
| `N8N_PUBLIC_URL` | URL public của n8n — để dựng link duyệt trong embed |

Credential Gmail (OAuth **của khách**) cấu hình trực tiếp trong node
"Gửi email khách cuối" — làm một lần khi onboard.

## Khi báo giá bị từ chối vì giá dầu cũ

`/tools/quote` trả **422** khi giá dầu được dùng để điều chỉnh mà đã cũ từ 7 ngày trở lên
(cảnh báo từ 2 ngày; đổi bằng `FUEL_PRICE_WARN_DAYS` / `FUEL_PRICE_MAX_DAYS` phía Brain).
Nghĩa là **đồng bộ giá dầu đã chết nhiều ngày** — mở `logistics_fuel_price_sync`, xem lần
chạy gần nhất (thường là regex bóc giá không còn khớp trang PVOIL). Không sửa bằng cách
nâng ngưỡng.

## Định dạng ngày trong Sheet

Mọi cột ngày (`valid_from`, `valid_to`, `FuelIndex.date`) phải là **YYYY-MM-DD** (đặt cột
kiểu "Văn bản thuần" để Google Sheets không tự đổi sang `DD/MM/YYYY` theo locale). Ô ngày có
chữ mà không đọc được thì giá/dòng đó **bị bỏ** và ghi vào `canh_bao_du_lieu`; ô để trống
nghĩa là không giới hạn. "Hôm nay" luôn là ngày **giờ Việt Nam (UTC+7)**.

## Ranh giới bảo mật (AGENTS.md R2)

- `internal_json` (biên, giá gốc nhà xe, điều chỉnh dầu) **chỉ** xuất hiện trong
  embed Discord nội bộ và cột Sheet — **không bao giờ** vào email khách cuối.
  Workflow approve dựng email **duy nhất từ phần công khai** (`quoted_price`,
  `surcharges`).
- Trước khi deploy: chạy thử `logistics_fuel_price_sync` một lần, xem HTML thật
  của trang PVOIL rồi chỉnh regex trong node "Bóc giá diesel" (đã đánh dấu TODO).
