# AI cho người chưa làm AI

> Viết cho thành viên mới của dự án ANSER chưa từng làm việc với mô hình ngôn ngữ.
> Không cần biết gì trước. Không có công thức toán nào.
>
> Mục đích: sau khi đọc, bạn **hiểu vì sao** dự án này được dựng như vậy, chứ không chỉ nhớ năm điều cấm. [SO_TAY_NGUOI_MOI.md §1.3](../SO_TAY_NGUOI_MOI.md) liệt kê năm ràng buộc; file này giải thích chúng đến từ đâu.

---

## 1. Mô hình ngôn ngữ thật ra làm gì

Hãy bắt đầu bằng thứ nó **không** làm.

Khi bạn gõ `2 + 2` vào máy tính bỏ túi, có một mạch điện cộng hai số. Kết quả `4` đến từ phép cộng.

Khi bạn gõ `2 + 2 bằng mấy` vào một mô hình ngôn ngữ, **không có phép cộng nào xảy ra**. Mô hình làm một việc khác hẳn: nó đoán chữ tiếp theo.

Nó đã đọc rất nhiều văn bản, và trong đống văn bản đó, sau cụm "2 + 2 bằng" thì chữ xuất hiện nhiều nhất là "4". Nên nó viết "4". Đúng — nhưng đúng vì **lý do khác** với máy tính bỏ túi.

Thử một ví dụ khác:

```
"Cước chuyến Hà Nội – Hải Phòng là 4.850.000đ, phụ phí cầu đường
 320.000đ. Tổng cộng là bao nhiêu?"
```

Mô hình sẽ trả về một con số. Con số đó **trông như** kết quả của phép cộng. Nó có thể là `5.170.000` — đúng. Nó cũng có thể là `5.150.000` — sai, nhưng vẫn trông hoàn toàn hợp lý: đúng độ lớn, đúng định dạng, đúng dấu chấm phân cách nghìn.

**Đó là điều cần nhớ.** Mô hình không sinh ra con số *đúng*; nó sinh ra con số *trông đúng*. Phần lớn thời gian hai thứ đó trùng nhau. Phần còn lại thì không, và bạn không có cách nào nhìn vào câu trả lời mà biết lần này là lần nào.

## 2. Vì sao "đúng 95%" không phải là 95% an toàn

Đây là chỗ trực giác thông thường dẫn người ta đi sai.

Với phần mềm bình thường, sai thì **ồn ào**: chương trình đổ, log đỏ, trang trắng. Bạn biết ngay có chuyện.

Với một con số sai trong báo cáo tài chính, không có gì ồn ào cả. Nó nằm im trong sổ sách. Người ta đọc, gật đầu, gửi báo giá cho khách, ghi vào sổ. **Lỗi chỉ lộ ra lúc quyết toán** — có thể là ba tháng sau, khi không ai còn nhớ con số đó từ đâu ra.

Nên với tầng kế toán, "mô hình đúng 95%" không đọc là "khá tốt". Nó đọc là: **cứ 20 bản ghi thì có 1 bản sai mà không ai biết**, và những bản ghi đó cộng dồn vào nhau.

Một sự cố thật của dự án, mã nội bộ **BR-01**: một khoản phụ phí bị bỏ im lặng trong lúc xử lý, và báo giá gửi cho khách bị sai. Không có thông báo lỗi nào. Mọi thứ trông bình thường cho tới khi có người đối chiếu tay.

Từ đó mới có câu kiểm tra mà mọi đề xuất trong dự án phải trả lời:

> **Nếu mô hình đọc sai một chữ số, có bản ghi sổ sách nào sai theo không?**

Nếu câu trả lời là có — thiết kế đó thiếu một lớp.

## 3. Vậy mô hình dùng để làm gì

Nếu không cho nó tính toán thì giữ nó làm gì? Vì nó rất giỏi đúng **một** việc mà code thường không làm nổi: **dịch qua lại giữa tiếng Việt và cấu trúc dữ liệu.**

Hai chiều, cả hai đều là việc ngôn ngữ:

**Chiều vào — tiếng người thành dữ liệu có cấu trúc.** Khách nhắn:

> *"cho anh báo giá xe 5 tấn chạy Hữu Nghị đi Hải Phòng thứ 5 tuần này, hàng lạnh nhé"*

Mô hình bóc ra:

```json
{"vehicle_type": "5T", "origin": "Hữu Nghị", "destination": "Hải Phòng",
 "cargo_type": "Hàng lạnh", "pickup_date": "2026-07-29"}
```

Viết code thường để hiểu câu đó thì cần hàng nghìn luật, và vẫn gãy khi khách viết "xe 5 tấn", "xe 5T", "5 tấn", "năm tấn", hay quên dấu.

**Chiều ra — dữ liệu thành tiếng người.** Code tính xong, cho ra một bảng số. Mô hình viết thành câu đọc được: *"Lãi gộp tháng này 11,5 triệu, giảm so với tháng trước chủ yếu vì chi phí nhiên liệu tăng."*

**Ở giữa hai chiều đó là Python.** Mọi phép tính — thuế, cước, biên lợi nhuận, lãi lỗ — nằm trong code thường, có unit test, chạy lại bao nhiêu lần cũng ra cùng một kết quả.

Đó chính là **R1**. Nó không phải một điều cấm tuỳ tiện; nó là hệ quả của việc hiểu mô hình làm gì.

## 4. Nhưng diễn giải cũng bịa được

Giả sử ta đã làm đúng R1: code tính ra con số, mô hình chỉ diễn giải. Xong chưa?

Chưa. Mô hình vẫn **đang viết chữ**, và chữ nó viết có thể chứa những con số không có trong dữ liệu bạn đưa.

Đo thật trên dự án: bản mô hình tinh chỉnh **bịa số ở 8–10 ca trên 27**. Không phải tính sai — mà viết ra một con số đơn giản là không tồn tại ở đâu cả.

Cách xử không phải là làm mô hình giỏi hơn. Cách xử là:

> **Hệ thống phải an toàn ngay cả khi mô hình sai.**

Nên có `src/core/grounding.py`: trước khi câu trả lời ra màn hình, một đoạn code thường soát mọi con số trong đó. Con số nào không có trong dữ liệu gốc thì **chặn cả câu trả lời** và thay bằng lời từ chối.

Thà không trả lời còn hơn trả lời sai mà nghe xuôi tai.

## 5. "Chưa biết" không phải là "bằng 0"

Đây là chỗ sai tinh vi nhất, và nó không phải lỗi của AI — nó là lỗi thiết kế mà AI làm cho dễ mắc hơn.

Báo cáo lãi lỗ cần giá vốn. Nếu một mặt hàng **chưa ai nhập giá vốn** thì giá vốn là *chưa biết*. Nếu code coi nó là `0`, phép tính thành:

```
lãi gộp = doanh thu − 0 = doanh thu
```

Ra một con số **rất đẹp**: lãi 100%. Và sai hoàn toàn.

Con số tài chính sai mà *nghe có vẻ đúng* là loại lỗi tệ nhất, vì không ai đi kiểm một tin vui. Nên `reporting.py` không điền 0: nó tính thêm `cogs_coverage_pct` (bao nhiêu phần doanh thu có giá vốn), hạ mức `confidence`, và ghi cảnh báo.

Quy tắc: `None` nghĩa là **chưa biết**, `0` nghĩa là **biết, và bằng không**. Gộp hai thứ là tạo ra đúng cái lỗi đang cố tránh.

## 6. Bốn ràng buộc còn lại, giờ đã dễ hiểu

### R2 — Chủ quyền dữ liệu

Gửi một câu hỏi tới mô hình của công ty khác (OpenAI, Google, DeepSeek) nghĩa là **gửi nội dung câu hỏi đó đi**. Nếu câu hỏi chứa bảng giá cước, danh sách khách, hay tỷ lệ biên lợi nhuận — bạn vừa đưa tài sản của khách hàng cho bên thứ ba.

Nên Brain chạy mô hình **trên máy của mình**. Ngoại lệ duy nhất là nguồn công khai một chiều: giá xăng, tỷ giá, thời tiết — và ngay cả khi tra những thứ đó, truy vấn gửi đi cũng bị lọc bỏ con số và tên khách trước.

### R3 — Ngân sách là ràng buộc thiết kế

Mô hình chạy trên card đồ hoạ, và card đồ hoạ tính tiền theo giờ. Trần cho giai đoạn pilot: **5 triệu đồng/tháng**, đang nhắm 750 nghìn.

Nên "dùng mô hình to hơn cho chắc" không phải một lựa chọn trung tính. Mọi đề xuất làm tăng chi phí phải kèm ba thứ: tăng bao nhiêu VNĐ/tháng, cải thiện chỉ số nghiệp vụ nào, và doanh thu nào trả cho phần tăng đó.

### R4 — Một nguồn sự thật

Không riêng AI, nhưng AI làm nó nguy hơn: **prompt cũng là một nơi chứa định nghĩa**. Nếu lược đồ cơ sở dữ liệu được chép vào một prompt, rồi lược đồ thật đổi, thì prompt đó dạy mô hình một thế giới không còn tồn tại — và **không có lỗi biên dịch nào báo cho bạn**.

Chuyện này đã xảy ra trong dự án nhiều lần. Xem `AGENTS.md` §R4 để thấy danh sách.

### R5 — Không gắn với phần cứng

Phần cứng hiện tại là GPU thuê, và sẽ đổi. Nếu tên card hay dung lượng bộ nhớ được viết thẳng vào code, chuyển máy là sửa code — rồi quên một chỗ, rồi hỏng ở chỗ không ai ngờ.

Mọi tham số phần cứng đọc từ biến môi trường. Tiêu chí nghiệm thu: **chuyển máy chỉ đổi file `.env`, không sửa dòng code nào.**

## 7. Tự kiểm

Trả lời được sáu câu này thì bạn đã nắm phần cốt lõi:

1. Vì sao con số do mô hình viết ra lại nguy hiểm hơn con số do code tính ra, dù cả hai đều có thể sai?
2. Mô hình giỏi hai việc gì trong hệ thống này?
3. `grounding.py` chặn cái gì, và vì sao chặn cả câu trả lời chứ không sửa riêng con số?
4. `None` và `0` khác nhau thế nào, và vì sao nhầm chúng lại tạo ra tin vui giả?
5. Vì sao không được gửi câu hỏi của khách tới một mô hình bên ngoài, kể cả "chỉ để thử"?
6. Câu kiểm tra phải hỏi trước mỗi lần commit là gì?

Không chắc câu nào thì đọc lại mục tương ứng, hoặc hỏi trong issue của việc bạn đang làm.

## 8. Đọc tiếp

| Muốn gì | Đọc đâu |
|---|---|
| Cài đặt và chạy được trên máy mình | [SO_TAY_NGUOI_MOI.md §2](../SO_TAY_NGUOI_MOI.md) |
| Code tổ chức thế nào | [SO_TAY_NGUOI_MOI.md §3](../SO_TAY_NGUOI_MOI.md) |
| Luật đầy đủ, bản chính thức | [AGENTS.md](../AGENTS.md) |
| Vì sao kiến trúc là như vậy | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| Cách viết tài liệu trong dự án | [docs/VIET-CHO-AI-DOC.md](VIET-CHO-AI-DOC.md) |
