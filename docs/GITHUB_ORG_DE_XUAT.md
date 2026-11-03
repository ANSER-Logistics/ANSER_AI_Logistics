# GitHub Organization ANSER — còn phải làm gì

> Cập nhật 04/11/2026. Người đọc: Sơn, và ai cần thao tác trên org.
> Việc ở đây làm trên trình duyệt, không cần biết lập trình.

Org đã lập, hai repo đã vào. **Còn bốn việc chưa xong**, mục 2.

Muốn biết vì sao lập org thì xem [mục 6](#6-vì-sao-lập-org-đã-quyết-xong) ở cuối — đó là chuyện đã quyết, để lại làm lịch sử.

---

## 1. Hiện trạng

| | Đường dẫn | Trạng thái |
|---|---|---|
| Org | [ANSER-Logistics](https://github.com/ANSER-Logistics) | lập 03/11/2026 |
| Brain | [ANSER_AI_Logistics](https://github.com/ANSER-Logistics/ANSER_AI_Logistics) | ✅ đã vào org, public |
| Body | [ANSER-logistics-body](https://github.com/ANSER-Logistics/ANSER-logistics-body) | ✅ đã vào org, public |
| Team `brain` | | ✅ đã tạo |
| Team `body` | | ✅ đã tạo |

**Cả hai repo phải giữ public.** Gói Free chỉ cho đầy đủ tính năng với repo public. Chuyển sang private là mất các cổng bảo vệ ở mục 2, và muốn giữ thì phải trả 4 USD mỗi người mỗi tháng.

---

## 2. Bốn việc chưa xong

### 2.1. Mở khoá GitHub Actions

**Hiện trạng:** repo Brain có **153 lượt chạy, không lượt nào xanh**, liên tục từ 14/05/2026. Mỗi lượt chết trong 2–3 giây, trước khi chạy bước nào.

**Nguyên nhân:** vào `Settings → Billing → Payment information` sẽ thấy dòng đỏ:

> Invalid payment method — authorization hold failed.

GitHub giữ thử một khoản nhỏ trên thẻ để xác thực rồi huỷ ngay. Lượt giữ đó hỏng, nên tài khoản bị coi là thanh toán lỗi và Actions bị chặn.

Trang `Billing → Overview` hiện `$0` và không có khoản phải trả — nhìn ở đó sẽ tưởng không có vấn đề gì. Hai trang nói hai chuyện khác nhau; trang `Payment information` mới đúng.

**Làm theo thứ tự:**

1. Bấm **Retry authorization** trên dải băng vàng.
2. Vẫn hỏng thì gọi ngân hàng, bật **thanh toán quốc tế / trực tuyến** cho thẻ. Nói rõ là "giao dịch giữ tiền xác thực từ GitHub" — thẻ nội địa Việt Nam hay chặn loại này mặc định. Rồi bấm Retry lần nữa.
3. Vẫn hỏng thì đổi thẻ khác, hoặc PayPal.
4. Vẫn hỏng thì mở phiếu hỗ trợ ở **GitHub Support → Billing**. Chỉ họ gỡ khoá thủ công được. Xem cả mục **Payment history** — một hoá đơn hỏng còn treo vẫn giữ cờ khoá dù thẻ đã sửa.

**Đáng làm vì:** repo public dùng máy chạy tiêu chuẩn là miễn phí. Gỡ được khoá thì 1254 bài kiểm tra của Brain có cổng tự động chạy lại, không tốn đồng nào.

**Chưa chắc chắn:** về lý thì gói Free + repo public không cần thẻ nào cả, nên gỡ thẻ ra là hết lỗi. Nhưng tài liệu chính thức chỉ nói phải có **một lượt xác thực thành công** thì mới tự mở khoá. Đừng gỡ thẻ với kỳ vọng nó chữa được.

### 2.2. Đưa file CODEOWNERS lên nhánh chính

**CODEOWNERS là gì:** một file liệt kê *đường dẫn nào thuộc về ai*. Khi có ai đó mở PR chạm vào đường dẫn khớp, GitHub tự thêm người hoặc nhóm đó làm người duyệt bắt buộc.

**Nó dùng để làm gì ở đây:** AGENTS.md §1 của Brain viết *"Body KHÔNG ĐƯỢC SỬA"*. Hôm nay đó là một câu trong file — ai quên là vi phạm, và không có gì chặn lại. CODEOWNERS biến nó thành thứ GitHub thi hành.

**Hiện trạng — cả hai repo đều chưa có file này trên nhánh chính:**

| Repo | File ở đâu | Có tác dụng chưa |
|---|---|---|
| Brain | nhánh `feat/workflow-format-and-deterministic-core` | ❌ chưa — nhánh mặc định là `main` |
| Body | đang nằm trong [PR #25](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/25) | ❌ chưa — chưa gộp |

**GitHub chỉ đọc CODEOWNERS từ nhánh mặc định.** File nằm trên nhánh khác thì không tính. Đây là chỗ hay nhầm nhất.

**Việc cần làm:** gộp nhánh Brain vào `main`, và đội Body quyết PR #25.

**Ba điều nữa hay nhầm:**

1. **Dòng khớp cuối cùng thắng** — ngược với `.gitignore`. Nên mẫu chung đặt trước, mẫu cụ thể đặt sau.
2. **Nhóm được nhắc phải có quyền Write trở lên** trên repo đó. Không thì GitHub bỏ qua dòng ấy **mà không báo lỗi** — file trông vẫn đúng, chỉ là không chạy.
3. **File này một mình không làm gì cả.** Nó chỉ là gợi ý người duyệt cho tới khi bật "Require review from Code Owners" ở mục 2.3.

**Kiểm xem có chạy không:** mở một PR nháp sửa một dòng trong `AGENTS.md`. Ô "Reviewers" phải tự điền nhóm `brain`. Không tự điền thì sai ở quyền nhóm hoặc sai cú pháp — `Settings → Code owners` liệt kê lỗi cú pháp.

### 2.3. Bật cổng bảo vệ nhánh chính

Hai repo đều chưa có. Hiện một lệnh `git push` là code vào thẳng nhánh chính, không ai nhìn.

Vào `Settings → Rules → Rulesets → New ruleset → New branch ruleset`:

| Ô | Điền |
|---|---|
| Ruleset Name | `bao-ve-nhanh-chinh` |
| Enforcement status | **Active** — để `Disabled` thì nó chỉ nằm đó |
| Bypass list | **để trống** |
| Target branches | `Add target → Include default branch` |

Rồi tích trong phần **Rules**:

- ☑ Require a pull request before merging
  - Required approvals: **1**
  - ☑ Require review from Code Owners
  - ☑ Dismiss stale pull request approvals when new commits are pushed
- ☑ Block force pushes
- ☐ Require status checks to pass — **chưa bật**, xem ghi chú dưới

**Đừng thêm mình vào Bypass list.** Thêm vào là tự vô hiệu hoá đúng cái vừa dựng.

**Đừng bật "Require status checks" trước khi xong việc 2.1.** Khi Actions còn khoá thì không lượt kiểm nào xanh được, mà luật này đòi kiểm xanh mới cho gộp — tức khoá luôn mọi PR, kể cả PR sửa chính cái khoá đó.

**Đội một người thì sao?** `Required approvals: 1` nghĩa là không ai tự duyệt PR của chính mình. Thành làm Brain một mình nên mọi PR sẽ cần anh duyệt. Thấy vướng thì để `0` mà vẫn bật "Require a pull request" — vẫn chặn đẩy thẳng, vẫn có chỗ đọc thay đổi, chỉ không bắt buộc người thứ hai.

### 2.4. Dựng cột cho bảng công việc

Bảng đã tạo: [ANSER - Brain va Body](https://github.com/orgs/ANSER-Logistics/projects/5). Trên đó đã có 5 mục, lấy từ **cả hai repo**:

| | |
|---|---|
| `ANSER_AI_Logistics#2` | S6 — Brain cần nguồn dòng bán/chi phí |
| `ANSER-logistics-body#23` · `#24` | hai việc bên Body mà S6 đang chờ |
| `ANSER-logistics-body#22` · `#25` | hai PR Brain gửi sang |

**Một bảng trải được hai repo.** Tài liệu bản trước để ngỏ câu hỏi này vì không tìm được tài liệu chính thức nào xác nhận. Giờ thử rồi: được.

**Còn phải làm bằng tay** — GitHub chưa cho đặt cột qua dòng lệnh:

1. Mở bảng → `Settings` → `Manage access` → thêm cả hai nhóm `brain` và `body`.
2. Đặt tên các cột trong trường `Status`.

Cột gợi ý: `Chờ quyết` · `Sẵn sàng` · `Đang làm` · `Chờ duyệt` · `Xong`.

Cột `Chờ quyết` hay bị thiếu nhất, mà phần lớn việc đứng là đứng ở đó — không phải vì khó, mà vì chưa ai quyết.

3. Bật chế độ cây: `View` → `Hierarchy`. Lúc đó `#23` và `#24` hiện lồng dưới `#2` thay vì nằm rời.

---

## 3. Những thứ đã dựng, và chúng làm gì

### Liên kết việc giữa hai repo

Một issue bên repo này gắn làm **con** của issue bên repo kia. Trạng thái việc con hiện ngay trên việc cha.

Đã dựng và kiểm chứng:

- [Brain#2](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/2) — "Brain cần nguồn dòng bán/chi phí từ Body"
- └ [Body#23](https://github.com/ANSER-Logistics/ANSER-logistics-body/issues/23) — API xuất dòng bán và chi phí
- └ [Body#24](https://github.com/ANSER-Logistics/ANSER-logistics-body/issues/24) — lược đồ logistics

Trước khi hai repo vào chung org, GitHub từ chối thẳng việc này: issue cha và con phải cùng một chủ sở hữu. Brain thuộc `PCBoiz`, Body thuộc `Dgsonn` — hai người khác nhau.

Đây là lý do kỹ thuật chính để lập org. Giờ chỗ chặn nhìn thấy được, thay vì nằm trong một dòng tài liệu.

### Phân quyền theo nhóm

Thêm người vào team `body` là họ có quyền trên mọi repo của Body. Bỏ khỏi org là mất sạch quyền ở mọi nơi — quan trọng khi có người nghỉ một thời gian.

Trước đây phải mời từng người vào từng repo một.

### Hai đề xuất đang chờ bên Body

- [Body#22](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/22) — sửa chỗ panel lợi nhuận hiện `0%` cho tình huống "chưa đo được"
- [Body#25](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/25) — thêm file `CODEOWNERS`

Cả hai là đề xuất. Đội Body đọc rồi tự quyết gộp hay đóng.

---

## 4. Việc nào của ai

| Việc | Ai làm | Chặn bởi |
|---|---|---|
| 2.1 — mở khoá Actions | **Sơn** | — |
| 2.2 — gộp nhánh Brain vào `main` để CODEOWNERS có tác dụng | **Sơn** | — |
| 2.2 — quyết [PR #25](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/25) (CODEOWNERS cho Body) | **đội Body** | — |
| 2.3 — bật cổng bảo vệ nhánh, repo Brain | **Sơn** | 2.2 |
| 2.3 — bật cổng bảo vệ nhánh, repo Body | **Dgsonn** | 2.2 |
| 2.4 — đặt tên cột + bật chế độ cây | **Sơn** | — |
| Quyết [PR #22](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/22) (sửa panel) | **đội Body** | — |

Hai chỗ có thứ tự bắt buộc:

- **2.2 phải trước 2.3.** Bật "Require review from Code Owners" khi chưa có file CODEOWNERS trên nhánh mặc định thì luật đó không biết hỏi ai.
- **2.1 phải trước khi bật "Require status checks".** Xem ghi chú ở mục 2.3.

Việc 2.1 làm được ngay hôm nay và nó quyết định phần còn lại đáng làm tới đâu.

---

## 5. Nếu có gì gãy

**Đường dẫn cũ vẫn chạy nhờ GitHub tự chuyển hướng**, nên mọi thứ *có vẻ* bình thường. Đó là lý do bước dọn hay bị bỏ qua, rồi gãy vài tuần sau khi ai đó tạo lại repo trùng tên ở chỗ cũ.

Trên máy từng người, trong thư mục repo:

```
git remote -v
git remote set-url origin https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git
git fetch origin
```

Repo Body thì đổi `ANSER_AI_Logistics` thành `ANSER-logistics-body`.

**Công cụ cần trỏ lại:**

| Thứ | Kiểm thế nào |
|---|---|
| grapuco | `grapuco status` — liên kết theo mã repo nên nhiều khả năng không gãy, nhưng kiểm |
| bảng kanzo `brain` | đang liên kết địa chỉ cũ `pcboiz/...`, phải trỏ lại |

**Tài liệu trong repo:** bảng tra cứu ở [`SO_TAY_NGUOI_MOI.md §1.2`](../SO_TAY_NGUOI_MOI.md) là chỗ phải đúng. Biên bản và bản phân việc trong [`docs/chu-ky-01/`](chu-ky-01/) để nguyên — đó là tài liệu lịch sử, sửa tên trong một biên bản đã ký là viết lại cái đã xảy ra.

---

## 6. Vì sao lập org (đã quyết xong)

Giữ lại để người đến sau biết căn cứ. Không cần đọc nếu chỉ cần làm việc ở mục 2.

**Gốc của đề xuất:** tin nhắn của Tiến Sĩ — *"đỡ mấy lần thêm thành viên, có cả quản lý công việc, kanban trên đấy"*.

**Vấn đề thật không phải thiếu tính năng, mà là hai chủ sở hữu khác nhau.** Brain thuộc `PCBoiz`, Body thuộc `Dgsonn`. GitHub ràng buộc nhiều thứ theo chủ sở hữu:

| Không làm được khi khác chủ | Org sửa thế nào |
|---|---|
| Gắn issue repo này làm con của issue repo kia | Hai repo cùng chủ, gắn được — xem mục 3 |
| Phân loại issue dùng chung | Phân loại định nghĩa ở cấp org, repo cá nhân không có |
| Thêm người một lần cho nhiều repo | Team |

**Chi phí: 0đ.** Gói Free cho org tính đủ tính năng với repo public, hạn chế với repo private. Cả hai repo đang public.

Điều kiện kèm theo: **giữ public**. Chuyển sang private là mất bảo vệ nhánh, `CODEOWNERS`, người duyệt bắt buộc. Muốn giữ phải lên gói Team, 4 USD mỗi người mỗi tháng — khoảng 420 nghìn đồng mỗi tháng cho bốn người, không nhỏ so với trần ngân sách hạ tầng 5 triệu.

Và nó chạm một chỗ đau: repo public chính là đường mật khẩu Neon đi ra hồi 27/07. Giữ public là lựa chọn có giá, không phải lựa chọn mặc định.

**Org không giải quyết được gì:** nó là cổng quyền, không phải kỷ luật. Tài liệu lệch khỏi code, định nghĩa trùng ở nhiều nơi, số liệu do model tự tính — org không bắt được cái nào. Nó làm cho việc **chạm vào phần của người khác** trở nên có cổng; không làm cho việc chạm vào phần của chính mình trở nên đúng.

---

## Nguồn

- [GitHub's plans](https://docs.github.com/en/get-started/learning-about-github/githubs-plans)
- [How use of GitHub Actions is measured](https://docs.github.com/billing/managing-billing-for-your-products/managing-billing-for-github-actions)
- [Update to GitHub Actions pricing (12/2025)](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)
- [Hierarchy view in GitHub Projects (01/2026)](https://github.blog/changelog/2026-01-15-hierarchy-view-now-available-in-github-projects/)
- [Manage sub-issues, types, and dependencies from GitHub CLI (06/2026)](https://github.blog/changelog/2026-06-10-manage-sub-issues-types-and-dependencies-from-github-cli/)
- [Invalid payment method — authorization hold failed](https://github.com/orgs/community/discussions/182510)
