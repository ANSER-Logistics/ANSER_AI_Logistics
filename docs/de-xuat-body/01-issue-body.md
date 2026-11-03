Panel lợi nhuận đang hiển thị **0% phủ giá vốn** trong trường hợp Brain thật ra đang nói "không đo được".

### Chỗ gây ra

`frontend/src/components/dashboard/BrainProfitPanel.tsx:69`

```tsx
const coverage = explain?.cogs_coverage_pct ?? 0;
```

`??` chỉ nhảy khi `null`/`undefined`, nên ba trạng thái bị gộp thành hai:

| Brain trả | Hiện ra | Đúng chưa |
|---|---|---|
| `87.5` | 87,5% | ✅ |
| `0` | 0% | ✅ đã đo, bằng không |
| `null` | **0%** | ❌ không đo được |

### Vì sao đáng sửa

R1 của dự án: *"Thiếu dữ liệu thì nói thiếu, không điền 0 — làm thế thì lãi gộp = doanh thu, một con số sai mà trông rất đẹp."*

`reporting.py` bên Brain cố ý tính `cogs_coverage_pct` và hạ `confidence` thay vì điền 0. Dòng `?? 0` vô hiệu hoá đúng cái cẩn thận đó ở bước cuối — bước người dùng nhìn thấy.

**Chính Body đã làm đúng điều này ở chỗ khác:** `BrainPartner.balance` khai `number | null` kèm chú thích *"`null` = CHƯA BIẾT số dư, không phải bằng 0"*. Đây chỉ là áp cùng nguyên tắc cho `cogs_coverage_pct`.

### Brain đã sửa phần của mình

Trước 04/11, nhánh không-có-dữ-liệu của `/tools/report` chỉ trả `{"note": …}` — thiếu cả bốn trường mà `BrainReport` khai là bắt buộc. Nay trả đủ:

```json
{ "cogs_coverage_pct": null, "confidence": "không có dữ liệu",
  "formula": "Không tính được: không có dòng bán hợp lệ nào.",
  "period_count": 0, "note": "Không có dữ liệu hợp lệ trong khoảng yêu cầu." }
```

Nên **ngay bây giờ, chưa cần đổi gì**, dòng 122 đã hiện `độ tin cậy: không có dữ liệu` thay vì chuỗi rỗng.

### Đề xuất

```tsx
const coverage = explain?.cogs_coverage_pct;
const coverageText = coverage == null ? "chưa đo được" : `${coverage.toFixed(1)}%`;
```

`== null` bắt cả `null` lẫn `undefined`, nên an toàn cả khi gặp Brain bản cũ.

Chỗ nào vẽ thanh tiến trình theo `coverage` thì ẩn đi khi `null` — một thanh dài 0% trông vẫn như một phép đo.

Và đổi kiểu `explain.cogs_coverage_pct` thành `number | null` để TypeScript bắt được chỗ nào quên xử lý.

### Mức ưu tiên

Không gấp — chỉ sai khi báo cáo rỗng. Nhưng thuộc đúng loại lỗi hai đội đã thống nhất là nguy hiểm nhất: sai mà nghe có vẻ đúng.

---

Lý lẽ đầy đủ: [`docs/DE_XUAT_BODY_01.md`](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/blob/feat/workflow-format-and-deterministic-core/docs/DE_XUAT_BODY_01.md) (repo Brain)

Phía Brain: `9211fbe`
