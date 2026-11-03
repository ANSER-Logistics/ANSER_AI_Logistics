# Đề xuất gửi đội Body — 01

> Soạn 04/11/2026 từ phía Brain. **Đây là văn bản đề xuất, không phải thay đổi đã làm.**
> AGENTS.md §1: Brain không được sửa repo Body, chỉ được đề xuất bằng văn bản.
>
> Người đọc: Dgsonn, Sĩ, Nam.
> Repo liên quan: `ANSER-Logistics/ANSER-logistics-body`, file `frontend/src/components/dashboard/BrainProfitPanel.tsx`.

## Tóm tắt một dòng

`BrainProfitPanel.tsx` dòng 69 hiển thị **0% phủ giá vốn** khi Brain thật ra đang nói "không đo được". Brain đã sửa phần của mình; phần còn lại nằm ở một ký tự `??`.

---

## Chuyện gì xảy ra

Panel lợi nhuận đọc `explain` từ `/tools/report`:

```tsx
// BrainProfitPanel.tsx:69
const coverage = explain?.cogs_coverage_pct ?? 0;
```

Toán tử `??` chỉ nhảy sang nhánh phải khi giá trị là `null` hoặc `undefined`. Nên:

| Brain trả về | `coverage` thành | Người dùng thấy |
|---|---|---|
| `87.5` | `87.5` | 87,5% — đúng |
| `0` | `0` | 0% — đúng, nghĩa là *đã đo, và bằng không* |
| `null` | **`0`** | 0% — **sai**, nghĩa là *không đo được* |

Ba trạng thái, hai cách hiển thị. Trạng thái "không biết" bị trình bày giống hệt trạng thái "biết, và bằng không".

## Vì sao điều này quan trọng với ANSER

Nguyên tắc R1 của dự án viết: *"Thiếu dữ liệu thì nói thiếu, không điền 0. `reporting.py` không coi giá vốn trống là 0 — làm thế thì lãi gộp = doanh thu, một con số sai mà trông rất đẹp."*

Brain cố ý tính `cogs_coverage_pct` và hạ `confidence` thay vì điền 0. Dòng `?? 0` ở Body vô hiệu hoá đúng cái cẩn thận đó ở bước cuối — bước mà người dùng nhìn thấy.

Con số tài chính sai mà *nghe có vẻ đúng* là loại không ai phát hiện tới lúc quyết toán.

## Brain đã sửa phần của mình

Trước 04/11/2026, khi không có dòng bán hợp lệ nào, `/tools/report` trả:

```json
{ "explain": { "note": "Không có dữ liệu hợp lệ trong khoảng yêu cầu." } }
```

Thiếu cả bốn trường mà `BrainReport` khai là bắt buộc. Kiểu TypeScript chỉ sống lúc biên dịch, nên lúc chạy chúng là `undefined` — không lỗi ở đâu cả, chỉ là:

- dòng 122 `độ tin cậy: {explain.confidence}` → hiện chuỗi rỗng
- dòng 179 `{explain.formula}` → hiện chuỗi rỗng
- dòng 69 → hiện 0%

Và `note` mà Brain viết ra thì Body không biết nên không hiển thị.

Nay Brain trả đủ bốn trường ở cả hai nhánh:

```json
{
  "explain": {
    "cogs_coverage_pct": null,
    "confidence": "không có dữ liệu",
    "formula": "Không tính được: không có dòng bán hợp lệ nào.",
    "period_count": 0,
    "note": "Không có dữ liệu hợp lệ trong khoảng yêu cầu."
  }
}
```

Nghĩa là **ngay bây giờ, chưa cần Body đổi gì**, dòng 122 đã hiện `độ tin cậy: không có dữ liệu` thay vì chuỗi rỗng. Đó là tín hiệu đến được mắt người dùng.

Còn lại đúng một chỗ Brain không với tới: dòng 69.

## Đề xuất

Phân biệt `null` với `0`:

```tsx
const coverage = explain?.cogs_coverage_pct;           // giữ nguyên null
const coverageText =
  coverage == null ? "chưa đo được" : `${coverage.toFixed(1)}%`;
```

`== null` (hai dấu bằng) bắt cả `null` lẫn `undefined`, nên vẫn an toàn nếu Brain cũ chưa kịp triển khai.

Chỗ nào vẽ thanh tiến trình theo `coverage` thì ẩn thanh đó đi khi `null`, thay bằng dòng chữ — một thanh dài 0% trông vẫn như một phép đo.

## Hai điểm cần hai đội thống nhất

1. **`cogs_coverage_pct` có thể là `null`.** Kiểu `BrainReport` hiện khai `explain: { cogs_coverage_pct: number; … }`. Nên đổi thành `number | null` để TypeScript bắt được chỗ nào quên xử lý — như đã làm với `balance: number | null` của `BrainPartner`, kèm chú thích *"`null` = CHƯA BIẾT số dư, không phải bằng 0"*. Cùng một nguyên tắc.

2. **`note` là trường tuỳ chọn.** Brain chỉ trả nó khi có điều cần nói bằng chữ. Hiển thị được thì tốt, không hiển thị cũng không sai.

## Việc này không gấp

Không ai mất tiền vì nó hôm nay — panel chỉ hiện sai khi báo cáo rỗng. Nhưng nó thuộc đúng loại lỗi mà cả hai đội đã thống nhất là nguy hiểm nhất, nên đáng xếp cùng nhóm với những chỗ đã cẩn thận ở `balance`.

---

## Phụ lục — cách đối chiếu lại

Brain có một lệnh soát hợp đồng **chiều yêu cầu** (Body gửi gì, Brain nhận gì):

```bash
python offline_training/doi_chieu_hop_dong_body.py
```

Nó chưa soát **chiều phản hồi** (Brain trả gì, Body đọc gì) — đó là chiều sinh ra chính vấn đề trong tài liệu này, và nó khó soát tự động hơn vì Body đọc giá trị ở nhiều component. Hiện đang soát bằng tay.
