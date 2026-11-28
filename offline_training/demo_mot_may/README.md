# Demo Brain–Body trên một máy

Chạy **nguyên cả chuỗi** trên một máy Windows, không cần Neon, không cần GPU, chỉ dữ liệu hư cấu:

| Thành phần | Ở đây chạy thế nào |
|---|---|
| Database của Body | PostgreSQL 17 portable (gói npm `embedded-postgres`), chạy đủ migration của Body |
| Driver database của Body (`@neondatabase/serverless`) | **không sửa mã Body**: cầu WebSocket TLS trên `127.0.0.1:443` chuyển giao thức Postgres sang cổng 5432 |
| Brain (dịch vụ AI) | `ENV=LOCAL`: công cụ tính toán chạy thật, **chat trả câu giả** (không có mô hình) |
| Body (ứng dụng web) | bản `master`, build production, cổng 3100 |

Token Brain–Body và khoá đăng nhập sinh ngẫu nhiên mỗi lần bật, chỉ nằm trong biến môi trường của tiến trình. Mọi dịch vụ **chỉ nghe `127.0.0.1`**: đừng mở cổng ra mạng hay qua đường hầm.

## Chạy

```powershell
powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\cai_demo.ps1    # một lần (vài phút, tải thư viện)
powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\bat_demo.ps1    # bật, gieo dữ liệu, tự kiểm (lần đầu khoảng 1-3 phút, sau đó khoảng 15 giây)
powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\tat_demo.ps1    # tắt
```

`bat_demo.ps1` kết thúc bằng hai bộ kiểm, cả hai phải báo `ĐẠT` (chat là `MOCK`):

- `kiem_tich_hop_body.py`: Brain nhìn từ phía Body, kể cả chạy nguyên văn `brain.ts` của Body.
- `kiem_qua_body.py`: qua chính API của Body như màn hình sẽ gọi: đăng nhập, trạng thái AI, nạp bảng tồn kho, so hai bản xuất, báo cáo lãi gộp **khớp đáp án tính độc lập** từ dữ liệu đã gieo, các trang dashboard.

`node offline_training\demo_mot_may\chup_man_hinh.mjs` đi lại kịch bản bằng Chrome ẩn và chụp ảnh từng bước vào `<gốc demo>\anh`.

Gốc demo mặc định `~\anser-demo` (đổi bằng `-Goc` hay biến `ANSER_DEMO`). Làm lại dữ liệu từ đầu: tắt demo, xoá `<gốc demo>\pgdata`, bật lại.

## Buổi demo

- Đăng nhập bằng nút **"Người dùng demo"**. Body chỉ cho **10 lần đăng nhập trong 15 phút** (tính cả lần đúng mật khẩu): đừng đăng nhập đi đăng nhập lại; lỡ bị khoá thì tắt bật lại.
- Sáng ngày demo bật bằng `bat_demo.ps1 -BuildLai`: trang chủ của Body là số **tại thời điểm build**.
- Soi tồn kho: *Quản lý kho* → tab **"Kiểm sổ từ Excel"** → chọn `<gốc demo>\file_mau\ton_kho_mau.xlsx` → **Kiểm sổ**: 8 phát hiện trên 7 mã.
- So hai bản: *Cảnh báo sổ sách* → ô cũ chọn `ton_kho_mau.xlsx`, ô mới chọn `ton_kho_mau_ban_sau.xlsx` → **So hai bản**: 3 chỗ số liệu đã đổi, 21.600.000đ.
- Lãi gộp: *Báo cáo* → chọn **Tháng** → **Tính lãi gộp**. Lãi gộp chỉ tính trên phần doanh thu **có giá vốn**, nên `doanh thu − giá vốn` có thể khác `lãi gộp`; giải thích đúng câu đó, đừng để khách tự trừ.
- **Đừng mở khung chat** (nút tròn góc phải): không có mô hình, khung chat hiện câu giả.

## Giới hạn

- Chỉ Windows (script PowerShell). Phần Node và Python chạy được trên Linux nhưng chưa viết script bật cho Linux.
- PostgreSQL cục bộ khác Neon ở độ trễ mạng; demo này không kiểm được hành vi Neon.
- Chat, đọc ảnh hoá đơn và hỏi tài liệu cần mô hình hoặc kho tri thức: không có trong demo này.
