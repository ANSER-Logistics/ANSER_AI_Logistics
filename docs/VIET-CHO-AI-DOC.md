# Viết cho ai đọc

Luật viết của dự án ANSER. Áp cho **mọi** thứ người khác phải đọc: PR, issue, tài liệu, báo cáo, bình luận — trong đội hay ngoài đội.

Chủ dự án chốt 04/11/2026, sau khi đọc một loạt PR và tài liệu mà người ngoài đội Brain không hiểu nổi.

---

## 1. Luật gốc: người đọc không biết thứ bạn biết

Trước khi viết một chữ, trả lời ba câu:

1. **Ai đọc?** Tên cụ thể, hoặc vai trò cụ thể.
2. **Họ biết sẵn những gì?** Liệt kê ra. Phần còn lại phải giải thích.
3. **Đọc xong họ làm gì?** Bấm cái gì, quyết cái gì, hay chỉ cần biết.

Không trả lời được câu nào thì chưa viết được.

### Đội Body không biết gì về Brain

Hai đội, hai repo, hai ngôn ngữ, hai bộ nghiệp vụ. Người bên Body không biết `R1` là gì, không biết `BR-01` là sự cố nào, không biết `reporting.py` làm gì, không biết `cogs_coverage_pct` được tính ra sao.

Viết cho họ mà dùng những chữ đó như chữ phổ thông là viết cho chính mình đọc.

**Mỗi PR hoặc issue gửi sang Body phải tự đứng được**, không bắt ai mở repo Brain ra tra. Tối thiểu có:

| Phần | Nội dung |
|---|---|
| Chuyện gì xảy ra | Mô tả bằng thứ **họ** nhìn thấy, không phải bằng tên hàm bên Brain |
| Vì sao đáng sửa | Hậu quả cụ thể cho người dùng cuối hoặc cho họ |
| Brain đã làm gì rồi | Để họ biết phần còn lại nhỏ cỡ nào |
| Họ cần làm gì | Rõ tới mức không phải hỏi lại |
| Chưa kiểm được gì | Nói thẳng, đừng để họ phát hiện |

Thuật ngữ riêng của Brain thì **giải thích ngay tại chỗ**, một câu. Đừng chỉ gắn link — người đang đọc PR lúc 11 giờ đêm sẽ không mở link.

> ❌ "Vi phạm R1, xem AGENTS §2."
> ✅ "Dự án có một nguyên tắc: thiếu dữ liệu thì phải nói là thiếu, không được điền 0. Điền 0 làm con số trông như đã đo."

---

## 2. Viết sao cho đọc được

Dự án theo bộ luật của [`petergyang/no-ai-slop`](https://github.com/petergyang/no-ai-slop) và văn phong giải thích của [tryemulate.ai](https://www.tryemulate.ai/). Phần dưới là thứ hay sai nhất, không phải toàn bộ.

### Cụ thể thắng trừu tượng

Tên, số, ngày tháng, cơ chế. Một câu có thể bê nguyên sang dự án khác mà vẫn đúng là một câu thừa.

> ❌ "Thay đổi này cải thiện đáng kể độ tin cậy của báo cáo."
> ✅ "Panel đang hiện 0% phủ giá vốn cho tình huống chưa đo được. Sau PR này nó hiện 'chưa đo được'."

### Chữ cấm

`tận dụng` · `tối ưu hoá` (khi không có số) · `mạnh mẽ` · `toàn diện` · `đột phá` · `cách mạng` · `nâng tầm` · `sâu sắc` · `đáng kể` (khi không có số) · `vô cùng quan trọng` · `then chốt`

Cấm luôn mấy cách mở đầu: *"Điều quan trọng cần lưu ý là"*, *"Nói một cách đơn giản"*, *"Trong bối cảnh hiện nay"*, *"Về cơ bản"*.

### Cấu trúc cấm

| Kiểu | Ví dụ | Thay bằng |
|---|---|---|
| Đối lập giả | "Đây không phải là X. Đây là Y." | Nói thẳng Y |
| Hắng giọng | "Vấn đề là thế này:" | Bỏ, nói luôn |
| Ra vẻ bí mật | "Điều mà hầu hết mọi người bỏ qua" | Bỏ, nêu điều đó |
| Dấu hai chấm kịch tính | "Phần hay nhất: nó tự học." | Viết thành câu bình thường |
| Mảnh vụn kịch tính | "Thế thôi. Đơn giản vậy." | Viết đủ câu |
| Kết bài triết lý | "Tương lai không đến. Nó đã ở đây." | Bỏ, kết ở câu cụ thể cuối cùng |
| Tổng kết thừa | "Tóm lại, ..." | Người ta vừa đọc xong, đừng kể lại |
| Nguồn mơ hồ | "Các chuyên gia cho rằng" | Nêu tên nguồn, hoặc bỏ câu đó |

### Hình thức

- **Không emoji trong tiêu đề.**
- Đừng bôi đậm rải rác giữa câu cho có nhịp.
- Hai câu văn xuôi đọc tốt hơn thì đừng làm bullet.
- Đừng đặt tiêu đề cho một mục dài hai câu.
- **Dấu gạch ngang dài (—):** văn ngắn thì không dùng. Văn dài 1–2 cái, khi nó thật sự hơn dấu phẩy hoặc dấu chấm.

### Nói thật về chỗ chưa biết

Ghi riêng ra cái gì đã đo, cái gì suy ra, cái gì chưa kiểm được. Đừng trộn vào nhau.

Và đừng viết thành một mục có tiêu đề "Những gì tôi đo được và những gì tôi chưa kiểm" — đó là cách **người viết** nghĩ. Người đọc chỉ cần một dòng đúng chỗ: *"Chưa chạy `npm run build` trên nhánh này."*

---

## 3. Một tài liệu, một việc

Lỗi hay gặp nhất không phải câu chữ, mà là nhồi ba tài liệu vào một file.

| Loại | Trả lời câu gì | Ai đọc |
|---|---|---|
| Bản luận | Có nên làm không? | Người quyết |
| Bản tra cứu | Thứ này hoạt động thế nào? | Người cần hiểu |
| Bản hướng dẫn | Tôi bấm vào đâu? | Người làm |

Trộn lại thì người cần bấm phải lội qua phần tranh luận họ không hỏi, còn người cần quyết phải lội qua các bước bấm.

**Quyết xong thì phần luận thành lịch sử.** Chuyển nó xuống cuối, hoặc sang file khác, hoặc bỏ. Để nguyên là bắt mọi người đọc sau phải đọc lại một cuộc tranh luận đã kết thúc.

---

## 4. Tự soát trước khi gửi

Đọc lại bản nháp và trả lời:

- [ ] Người đọc mở ra, trong 10 giây có biết việc của mình là gì không?
- [ ] Có thuật ngữ nào của đội kia không hiểu mà chưa giải thích tại chỗ không?
- [ ] Có câu nào bê sang dự án khác vẫn đúng không? Xoá.
- [ ] Mỗi khẳng định có kèm số, tên, hoặc cơ chế không?
- [ ] Chỗ chưa kiểm được đã nói ra chưa?
- [ ] File này đang trả lời **một** câu hỏi hay ba?

### Nhờ máy soát hộ

```
Đọc file X theo docs/VIET-CHO-AI-DOC.md. Với mỗi chỗ vi phạm:
trích nguyên câu, nêu tên luật, đề xuất câu thay thế. Đừng viết lại cả file.
```

Soát trước, sửa sau. Viết lại cả file thì mất luôn giọng người viết — đó là thứ `no-ai-slop` cảnh báo ngay ở đầu.

---

## 5. Giữ giọng người viết

Luật này để **dễ đọc hơn**, không phải để mọi đoạn văn đều mượt như nhau.

Giữ nguyên: câu nói thẳng, chỗ thừa nhận mình chưa biết, câu dài theo nhịp nói, chỗ rẽ ngang có ích. Một bản nháp có giọng người, sau khi sửa, vẫn phải nghe ra là người đó viết.

Thứ cần cắt là thứ làm khó đọc: biệt ngữ không giải thích, câu dài rối, danh từ trừu tượng, cấu trúc rối rắm.
