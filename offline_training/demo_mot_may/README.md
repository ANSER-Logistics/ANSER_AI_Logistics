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

## Có model thật: Brain và mô hình trên Google Colab Pro

Máy này **không nạp model nào** (hết bộ nhớ). Brain, hai mô hình và kho tri thức chạy trên Colab; máy này chỉ chạy Body và database.

1. Colab: notebook mới, **Runtime → Change runtime type → GPU L4** (hoặc A100), một ô:

   ```python
   from google.colab import drive; drive.mount("/content/drive")
   !rm -rf /content/ANSER_AI && git clone -q --depth 1 -b feat/tich-hop-body https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git /content/ANSER_AI
   %run -i /content/ANSER_AI/offline_training/demo_colab.py
   ```

   Ô cài vLLM, chép trọng số từ Drive (`anser-v5-awq`, `q25vl7b-w4a16-tu-luong-tu`), bật hai server và Brain, **tự thử** (chat, đọc hai ảnh hoá đơn, nạp và hỏi tài liệu), mở đường hầm (ngrok nếu có `NGROK_AUTHTOKEN` trong Colab Secrets, không thì cloudflared) rồi giữ phiên sống. Lần đầu khoảng 15 đến 25 phút. Kết quả và log ghi vào `MyDrive/ANSER_AI_Logistics/demo_colab_<ngày>_<commit>/` (không có token).
   L4 và A100 hết (Colab tự đổi sang **T4**, 15 GB) thì ô chạy chế độ **chỉ chữ**: chat và hỏi tài liệu, **không đọc ảnh hoá đơn** (chưa đo chất lượng trên cấu hình này). Chạy trên **A100** thì hai mô hình vẫn bị bó trong lượng VRAM của một **L4 24 GB** (trần của production) và ô báo đỉnh VRAM so với 92% mức đó (dòng `vua_gpu_dich`).
2. Ô in hai dòng `BRAIN_URL=…`, `BRAIN_API_TOKEN=…`. Dán vào tệp mới `<gốc demo>\brain_colab.env` (ngoài repo, đừng gửi cho ai; đổi mỗi lần chạy lại ô).
3. Máy này:

   ```powershell
   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\tat_demo.ps1 -Goc <gốc demo>
   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\bat_demo.ps1 -Goc <gốc demo> -BrainColab <gốc demo>\brain_colab.env
   ```

   Hai bộ kiểm cuối chạy chế độ có model (`--can-model`, `--co-model`): chat phải do model trả lời, ảnh hoá đơn và tài liệu phải đạt.
4. Xong demo: bấm dừng ô Colab (đóng hầm, tắt server, khỏi tốn compute unit).

**Giới hạn của cách này.** Colab dành cho tính toán tương tác; [FAQ](https://research.google.com/colaboratory/faq.html) cấm "web service offerings not related to interactive compute" và "connecting to remote proxies" (đọc 28/11/2026). Chỉ dùng để thử và demo do chính mình điều khiển, không đưa địa chỉ cho khách, tắt khi xong; Colab có thể ngắt phiên bất cứ lúc nào (khi đó bật lại demo không có `-BrainColab` để còn phần tính bằng mã). **Chỉ dữ liệu hư cấu**: câu hỏi, ảnh và tài liệu đi qua đường hầm của bên thứ ba. Phục vụ khách thật vẫn là máy có GPU riêng (`deploy/`).

## Buổi demo

- Đăng nhập bằng nút **"Người dùng demo"**. Body chỉ cho **10 lần đăng nhập trong 15 phút** (tính cả lần đúng mật khẩu): đừng đăng nhập đi đăng nhập lại; lỡ bị khoá thì tắt bật lại.
- Sáng ngày demo bật bằng `bat_demo.ps1 -BuildLai`: trang chủ của Body là số **tại thời điểm build**.
- Soi tồn kho: *Quản lý kho* → tab **"Kiểm sổ từ Excel"** → chọn `<gốc demo>\file_mau\ton_kho_mau.xlsx` → **Kiểm sổ**: 8 phát hiện trên 7 mã.
- So hai bản: *Cảnh báo sổ sách* → ô cũ chọn `ton_kho_mau.xlsx`, ô mới chọn `ton_kho_mau_ban_sau.xlsx` → **So hai bản**: 3 chỗ số liệu đã đổi, 21.600.000đ.
- Dòng tiền: *Dòng tiền* → ô trái chọn `khach_hang_mau.xlsx` → **Soi ngay**, rồi chọn `nha_cung_cap_mau.xlsx` → **Soi ngay**; ô phải chọn `ton_kho_mau.xlsx` → **Nạp tồn kho**. Khách đang nợ 520.000.000đ, nợ nhà cung cấp 150.000.000đ, hàng trong kho và số ngày giá vốn; 7 điểm cần xem (khách tập trung, số dư âm, mã số thuế sai hay thiếu, trùng mã số thuế).
- Lãi gộp: *Báo cáo* → chọn **Tháng** → **Tính lãi gộp**. Lãi gộp chỉ tính trên phần doanh thu **có giá vốn**, nên `doanh thu − giá vốn` có thể khác `lãi gộp`; giải thích đúng câu đó, đừng để khách tự trừ.
- **Có `-BrainColab`:** *Tài liệu* → nạp `file_mau\quy_che_cong_no_mau.txt` → mở khung chat (nút tròn góc phải) hỏi "Theo quy chế bán hàng trả chậm, đại lý cấp 1 được trả chậm tối đa bao nhiêu ngày?" (đáp án **45**); *Tài liệu* → đọc ảnh `file_mau\hoa_don_cuoc_mau.png` (tổng 5.184.000, không cần xem lại) rồi `file_mau\hoa_don_cuoc_mau_sai_tong.png` (in 5.284.000, hệ thống đòi người xem vì tính lại ra 5.184.000).
- **Không có `-BrainColab`:** đừng mở khung chat (câu giả), đừng nạp tài liệu hay ảnh hoá đơn (kho tri thức tắt, không có mô hình đọc ảnh).
- Đừng bấm **Chạy** ở trang *Tự động hoá* (không có n8n).
- Soát thuế suất: *Cảnh báo sổ sách* → tab **"Thuế suất từng mã hàng"** → `file_mau\danh_muc_hang_hoa_mau.xlsx` → **Soát thuế suất**: 10 mã, 6 diện 8%, ô "Cần kế toán xác nhận" 4 (2 giữ 10%: thép tấm, phí bảo hiểm; 2 bảng tra không kết luận: mỡ bò, ắc quy). **Nói rõ đây là đề xuất để kế toán xác nhận**: mức 8% cho dầu mỡ bôi trơn dựa trên NQ 204/2025/QH15 và NĐ 174/2025/NĐ-CP (hiệu lực đến 31/12/2026), mới đối chiếu qua [nguồn thứ cấp](https://thuvienphapluat.vn/ma-so-thue/phap-luat-thue/dau-boi-tron-co-duoc-giam-thue-gtgt-8-den-het-ngay-31122026-211674.html), chưa có kế toán duyệt. Đừng nạp danh mục thật có phụ tùng (lọc nhớt, bơm dầu...): bảng tra hiện xếp một số tên đó vào diện 8% với lý do "dầu mỡ bôi trơn".

## Giới hạn

- Chỉ Windows (script PowerShell). Phần Node và Python chạy được trên Linux nhưng chưa viết script bật cho Linux.
- PostgreSQL cục bộ khác Neon ở độ trễ mạng; demo này không kiểm được hành vi Neon.
- Chat, đọc ảnh hoá đơn và hỏi tài liệu chỉ có khi Brain chạy trên Colab (mục "Có model thật").
