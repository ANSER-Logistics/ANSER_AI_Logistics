# GitHub Organization cho ANSER — nên hay không, và được gì

> Soạn 03/11/2026. Người đọc: Sơn, Thành (Brain), Sĩ và Nam (Body).
> Gốc của đề xuất: tin nhắn của Tiến Sĩ — *"đỡ mấy lần thêm thành viên, có cả quản lý công việc, kanban trên đấy"*.

Trả lời ngắn: **nên lập, chi phí 0đ, nhưng kèm một điều kiện ràng buộc phải biết trước khi ký.**

Dưới đây là những gì tôi đo được, những gì tôi suy ra, và những gì tôi **chưa** kiểm được — tách bạch ba loại.

---

## 1. Hiện trạng, đo lúc 03/11/2026

| | Brain | Body |
|---|---|---|
| Remote | `PCBoiz/ANSER_AI_Logistics` | `Dgsonn/ANSER-logistics` |
| Chủ sở hữu | `PCBoiz` (tài khoản cá nhân) | `Dgsonn` (tài khoản cá nhân) |
| Hiển thị | **public** | **public** |
| Push gần nhất | 03/11/2026 | 01/11/2026 |

Đo bằng `api.github.com`, không cần đăng nhập.

**Body đã đổi tên.** `Dgsonn/ANSER-v2` giờ là `Dgsonn/ANSER-logistics`. GitHub vẫn redirect tên cũ (HTTP 301), nên chưa ai gãy — nhưng mọi tài liệu trong repo Brain còn ghi `ANSER-v2` thì đang ghi tên quá hạn. AGENTS.md §1 là một trong số đó.

**Hai chủ sở hữu khác nhau là gốc của mọi hạn chế ở mục 2.** Không phải thiếu tính năng, mà là GitHub ràng buộc theo owner.

---

## 2. Ba thứ hiện không làm được, và org sửa đúng chúng

### 2.1. Liên kết việc Brain ↔ việc Body

Sub-issue cho phép gắn một issue làm con của issue khác, tối đa 100 con mỗi cha và 8 tầng. Nó **cho phép lấy issue từ repo khác**, nhưng REST API đòi repo cha và repo con **cùng một owner**.

`PCBoiz` ≠ `Dgsonn`, nên hiện tại không có cách nào nói *"BR-06 của Brain bị chặn bởi việc lược đồ logistics bên Body"* bằng cấu trúc. Nó chỉ sống trong văn bản, như AGENTS.md §8 đang ghi S6 là "⚪ Chặn".

Org làm hai repo cùng owner, và quan hệ chặn đó trở thành dữ liệu GitHub hiểu được.

### 2.2. Issue type

Issue type (Task / Bug / Feature mặc định, tự thêm tới 25 loại) định nghĩa **ở cấp org** và dùng chung cho mọi repo trong org. Repo thuộc tài khoản cá nhân **không có** tính năng này.

Với dự án hai thành phần, loại việc là thứ hay nhầm nhất. Một bộ type dùng chung cho cả Brain lẫn Body đáng giá hơn là quy ước nhãn viết tay ở hai nơi.

### 2.3. Thêm người

Đúng như Tiến Sĩ nói. Hiện mỗi người phải được mời vào **từng repo một**. Org có team: thêm người vào team `body` là họ có quyền trên mọi repo của Body, bỏ khỏi org là mất sạch quyền ở mọi nơi — quan trọng khi có người xin off một thời gian.

---

## 3. Chi phí: 0đ/tháng — nhưng có điều kiện

GitHub Free cho org: public repo được **đầy đủ tính năng**, private repo được **tập tính năng hạn chế**.

Những thứ Free **không** cho với repo private, chỉ có từ gói Team ($4/người/tháng):

- protected branches
- CODEOWNERS
- required reviewers / multiple reviewers
- wikis, security overview, repository insights

**Cả hai repo ANSER đang public, nên dùng được hết, miễn phí.**

Đây là điều kiện ràng buộc phải biết trước: **lập org trên gói Free nghĩa là cam kết giữ hai repo public.** Ngày nào chuyển sang private, toàn bộ mục 4 dưới đây tắt, và muốn giữ thì phải trả Team cho từng người.

Theo R3 (trần 5.000.000đ/tháng, mục tiêu hiện tại ~750.000đ), 4 người × $4 ≈ 420.000đ/tháng là khoản không nhỏ so với ngân sách GPU. Nên quyết định public/private là quyết định ngân sách, không chỉ là quyết định bảo mật.

**Và nó va vào R2b.** Repo public chính là đường mà mật khẩu Neon đi ra ngoài hồi 27/07. Giữ public là lựa chọn có giá, không phải lựa chọn mặc định. Bù lại: push protection của secret scanning miễn phí cho repo public, và hook `quet_secret_pre_commit.py` đã có sẵn ở Brain — nên hàng rào không phải không có.

---

## 4. Những gì bật được ngay sau khi có org, vẫn 0đ

Vì repo public:

- **Ruleset / protected branch cho `main`.** Hiện `main` của Brain không có gì chặn. Một ruleset đòi PR mới merge được là cổng rẻ nhất chặn commit thẳng.
- **CODEOWNERS.** Đây là thứ đáng giá nhất cho ANSER. AGENTS.md §1 viết *"Body KHÔNG ĐƯỢC SỬA, chỉ được đề xuất thay đổi bằng văn bản"* — hiện là quy tắc con người, ai quên là vi phạm. CODEOWNERS biến nó thành cổng kỹ thuật: PR chạm thư mục Body bắt buộc có người của team `body` duyệt.
- **Required reviewers.** Khớp trực tiếp với giao thức phản biện ở AGENTS.md §5.2.
- **Projects (bảng kanban).** Phần Tiến Sĩ nhắc tới.

---

## 5. Khả năng gỡ được CI đang chết — giả thuyết, chưa kiểm

BIEN_BAN_CHU_KY_01 mục 6 ghi: GitHub Actions của Brain có **136 lượt chạy, 0 lượt xanh**, mọi job dừng ở *"your account is locked due to a billing issue"*. Nghĩa là không cổng tự động nào đang hoạt động, và mọi câu "CI xanh" trong tài liệu cũ không có lượt chạy nào chứng minh. Đó là lý do `.pre-commit-config.yaml` ra đời — một phương án tạm trên máy dev.

Nhưng: **standard GitHub-hosted runner trên public repo là miễn phí**, không tiêu quota compute. Cả changelog 12/2025 lẫn trang billing chính thức đều nói vậy.

Nếu CI miễn phí mà vẫn bị khoá, thì khoá nằm ở **cấp tài khoản**, không phải cấp repo hay do hết tiền chạy. Một org mới có thiết lập billing riêng, nên **có thể** chạy lại được ngay, 0đ.

**Tôi không kiểm chứng được điều này.** Tôi không có quyền vào trang billing của tài khoản `PCBoiz`. Cần Sơn mở Settings → Billing and plans và đọc lý do khoá thật sự. Nếu là thẻ thanh toán lỗi ở cấp tài khoản, org có thể vẫn kế thừa vấn đề.

Nhưng nếu đúng, đây là lợi ích lớn nhất trong cả bản này — lớn hơn kanban: **135 file, 1163 test có cổng tự động chạy lại.**

---

## 6. Chỗ tôi không tìm được bằng chứng

- **Một bảng Projects v2 trải nhiều repo.** Hierarchy view (sub-issue tới 8 tầng, gom/lọc/sắp xếp vẫn giữ cây) đã GA 01/2026. Nhưng tôi không tìm được tài liệu chính thức nào xác nhận rõ một board trải nhiều repo hoạt động thế nào trong 2026. Nhiều nguồn ngầm giả định là được. **Tôi không khẳng định.** Việc này kiểm trong 10 phút sau khi có org, rẻ hơn tranh luận.
- **Dung lượng Packages của org trên Free.** Tài liệu chỉ nêu 500MB cho tài khoản cá nhân. ANSER chưa dùng Packages nên chưa thành vấn đề.

---

## 7. Đề xuất cụ thể

1. Lập org (tên gợi ý `anser-ai`). Miễn phí, không cần thẻ.
2. **Transfer** cả hai repo vào org — không phải fork, không phải clone. Transfer giữ nguyên issues, PR, lịch sử, và tự redirect URL cũ. Body vừa đổi tên nên cả đội đã thấy redirect của GitHub hoạt động thế nào.
3. Hai team: `brain`, `body`. Thành vào `brain`; Sĩ, Sơn, Nam vào `body`. Sơn là owner của org.
4. Thêm `CODEOWNERS` ở mỗi repo, chốt ranh giới AGENTS.md §1 bằng kỹ thuật.
5. Ruleset cho `main`: bắt buộc qua PR, bắt buộc 1 người duyệt.
6. Một Projects board chung. Kiểm luôn câu hỏi ở mục 6.1.
7. Sửa mọi chỗ còn ghi `ANSER-v2` thành `ANSER-logistics`, bắt đầu từ AGENTS.md §1.

---

## 8. Rủi ro khi transfer — đọc trước khi bấm

- **Chỉ chủ sở hữu transfer được repo của mình.** Sơn không transfer hộ `Dgsonn/ANSER-logistics` được; Dgsonn phải tự làm. Cần hai người cùng đồng ý, không phải một.
- **Remote cục bộ của mọi người cần cập nhật.** URL cũ redirect nên `git push` vẫn chạy một thời gian, nhưng đừng dựa vào đó — `git remote set-url` ngay.
- **Grapuco vừa link vào Brain theo `repoId`** (xem `.grapuco/config.json`). `repoId` không đổi theo tên repo nên khả năng cao không gãy, nhưng kiểm lại bằng `grapuco status` sau khi transfer.
- **Bảng kanzo `brain` đang liên kết `pcboiz/anser_ai_logistics`.** Phải trỏ lại sau transfer.
- **GitHub App / webhook / secret của repo** có thể cần cấp quyền lại. Brain hiện không có secret nào trong Actions nên phần này nhẹ.
- **Transfer không gỡ được credential đã lộ trong lịch sử.** R2b: credential đã lộ là credential đã chết. Lịch sử đi theo repo sang org nguyên vẹn. Đã quét toàn bộ lịch sử trước đây, mọi kết quả khớp đều là fixture của test — nhưng quét lại trước khi transfer là 2 phút, nên cứ quét.

---

## 9. Cái org không giải quyết

Org là cổng quyền, không phải kỷ luật.

- Lệch giữa tài liệu và code (ARCHITECTURE.md từng lệch nhiều tháng và dẫn tới chọn model theo phần cứng không có thật) — org không bắt được.
- R4 "một định dạng, một nguồn sự thật": `prompts.py` ↔ `agent_middleware.py` ↔ `chat.py::_validate_workflow` phải khớp nhau. CODEOWNERS bắt được PR chạm vào chúng, nhưng vẫn cần người đọc.
- R1 và R2 — LLM có lén tính toán không, payload có chứa dữ liệu khách không — vẫn là việc của người review.

Org làm cho việc **chạm vào phần của người khác** trở nên có cổng. Nó không làm cho việc chạm vào phần của chính mình trở nên đúng.

---

## 10. Làm từng bước

Thứ tự này có lý do: mỗi bước kiểm được trước khi sang bước sau, và bước nào hỏng thì lùi lại được mà chưa ai mất việc.

### Bước 0 — trả lời câu hỏi billing trước

**Làm trước mọi thứ khác**, vì câu trả lời quyết định org đáng giá đến đâu.

Mở `github.com/settings/billing` bằng tài khoản `PCBoiz`. Đọc lý do khoá.

- Nếu là **thẻ thanh toán lỗi / hết hạn** ở cấp tài khoản → org mới có billing riêng, nhiều khả năng CI chạy lại được ngay, 0đ (repo public dùng standard runner miễn phí).
- Nếu là **tranh chấp / vi phạm điều khoản** → org cùng chủ có thể kế thừa. Hỏi GitHub Support trước khi transfer.

Ghi lại nguyên văn dòng lý do rồi báo lại — tôi không có quyền vào trang đó.

### Bước 1 — lập org (2 phút, không cần thẻ)

`github.com/organizations/plan` → **Free** → đặt tên.

- Tên đề xuất: `anser-ai`. Phải là tên chưa ai dùng trên toàn GitHub.
- "This organization belongs to": chọn **My personal account**, không phải business — business hỏi thông tin doanh nghiệp và không cần cho gói Free.
- Email liên hệ: email anh đang dùng cho GitHub.

Chưa mời ai ở bước này.

### Bước 2 — tạo hai team

`github.com/orgs/anser-ai/teams` → **New team**, làm hai lần:

| Team | Thành viên | Quyền mặc định |
|---|---|---|
| `brain` | Thành | Write |
| `body` | Sĩ, Nam, (Sơn) | Write |

Anh là **Owner** của org, không cần ở trong team nào.

Đừng đặt quyền Admin cho team. Admin cho phép xoá repo và đổi hiển thị public/private — thứ mục 3 nói là không được đổi.

### Bước 3 — transfer repo Brain

`github.com/PCBoiz/ANSER_AI_Logistics/settings` → cuối trang, **Danger Zone** → **Transfer ownership** → gõ `anser-ai`.

Trước khi bấm, chạy lại một lượt quét bí mật trên toàn bộ lịch sử (R2b.2 — transfer giữ nguyên mọi commit):

```bash
git log --all -S 'npg_' --oneline | head
git log --all -S 'postgres://' --oneline | head
git log --all -S 'sk-' --oneline | head
```

Lần quét trước mọi kết quả khớp đều là fixture của test. Hai phút, cứ quét lại.

Sau khi transfer, trên **máy của từng người**:

```bash
git remote set-url origin https://github.com/anser-ai/ANSER_AI_Logistics.git
git remote -v        # xác nhận
```

URL cũ vẫn redirect, nhưng đừng dựa vào đó.

### Bước 4 — transfer repo Body

**Việc này chỉ Dgsonn làm được.** Anh không transfer hộ repo của người khác.

Cùng đường: `Settings` → `Danger Zone` → `Transfer ownership` → `anser-ai`.

Dgsonn cần được mời vào org trước (ít nhất quyền Member) thì mới chọn được org làm đích.

### Bước 5 — gán quyền repo cho team

Ở mỗi repo: `Settings` → `Collaborators and teams` → **Add teams**.

- `ANSER_AI_Logistics` → team `brain`: **Write**; team `body`: **Read**
- `ANSER-logistics` → team `body`: **Write**; team `brain`: **Read**

**Read cho đội kia là có chủ ý.** AGENTS.md §1 nói Brain không được sửa Body. Đến đây nó không còn là quy tắc giấy nữa — GitHub chặn thật. Nhưng vẫn đọc được, mà đọc là cần: lược đồ Body là nguồn sự thật cho `SCHEMA MAP` bên Brain.

### Bước 6 — CODEOWNERS

Tạo `.github/CODEOWNERS` ở mỗi repo.

Brain:

```
*                       @anser-ai/brain
/src/core/prompts.py    @anser-ai/brain
/AGENTS.md              @anser-ai/brain
```

Body: tương tự với `@anser-ai/body`.

File này chỉ có tác dụng khi bật "Require review from Code Owners" ở bước 7.

### Bước 7 — ruleset cho `main` / `master`

`Settings` → `Rules` → `Rulesets` → **New branch ruleset**.

- Target: `main` (Brain) / `master` (Body)
- Bật: **Require a pull request before merging** → required approvals **1** → **Require review from Code Owners**
- Bật: **Block force pushes**
- Chưa bật "Require status checks" cho tới khi CI chạy lại được — bật sớm là tự khoá mình, vì không check nào xanh nổi.

### Bước 8 — issue type và board

`Settings` của org → **Issue types**. Mặc định có Task / Bug / Feature. Thêm cái thật sự thiếu:

- `R-violation` — vi phạm R1–R5. Loại này không được để lẫn với bug thường.
- `blocked-by-other-repo` — việc Brain chờ Body hoặc ngược lại. Đây chính là thứ hiện không ghi được bằng cấu trúc.

Rồi `Projects` → **New project** → Board. Thêm cả hai repo vào nó.

**Kiểm ngay ở bước này** câu hỏi mục 6: một board có trải được hai repo không. Tôi không tìm được tài liệu chính thức xác nhận, và 10 phút thử rẻ hơn mọi tranh luận.

### Bước 9 — dọn những thứ trỏ vào địa chỉ cũ

- `.grapuco/config.json`: chạy `grapuco status`. `repoId` không đổi theo tên repo nên nhiều khả năng không gãy — nhưng kiểm.
- Bảng kanzo `brain`: đang liên kết `pcboiz/anser_ai_logistics`, phải trỏ lại.
- Tài liệu trong repo còn ghi `PCBoiz/...`: bảng tra cứu ở `SO_TAY_NGUOI_MOI.md §1.2` là chỗ phải đúng. Biên bản và bản phân việc cũ thì để nguyên — đó là tài liệu lịch sử.

### Bước 10 — kiểm lại bước 0

Vào `Actions` của repo Brain, chạy lại một workflow bất kỳ.

Xanh → đã gỡ được cổng tự động, và `.pre-commit-config.yaml` từ phương án tạm thành lớp thứ hai.
Vẫn khoá → quay lại kết luận ở bước 0 và hỏi GitHub Support.

---

## 11. Việc nào của ai

| Bước | Ai làm | Chặn bởi |
|---|---|---|
| 0 — đọc lý do khoá billing | **Sơn** | — |
| 1, 2 — lập org, tạo team | **Sơn** | — |
| 3 — transfer Brain | **Sơn** | bước 1 |
| 4 — transfer Body | **Dgsonn** | bước 1 + được mời vào org |
| 5, 6, 7 — quyền, CODEOWNERS, ruleset | **Sơn** | bước 3, 4 |
| 8 — issue type, board | **Sơn** | bước 1 |
| 9 — dọn địa chỉ cũ | mỗi người trên máy mình | bước 3, 4 |
| 10 — kiểm CI | **Sơn** | bước 3 |

Bước 0 làm được ngay hôm nay và nó quyết định mức độ đáng làm của tất cả phần còn lại.

## Nguồn

- [GitHub's plans — docs.github.com](https://docs.github.com/en/get-started/learning-about-github/githubs-plans)
- [How use of GitHub Actions is measured — docs.github.com](https://docs.github.com/billing/managing-billing-for-your-products/managing-billing-for-github-actions)
- [Update to GitHub Actions pricing — GitHub Changelog, 12/2025](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)
- [Hierarchy view now available in GitHub Projects — GitHub Changelog, 01/2026](https://github.blog/changelog/2026-01-15-hierarchy-view-now-available-in-github-projects/)
- [Manage sub-issues, types, and dependencies from GitHub CLI — GitHub Changelog, 06/2026](https://github.blog/changelog/2026-06-10-manage-sub-issues-types-and-dependencies-from-github-cli/)
- [Evolving GitHub Issues and Projects (GA) — community discussion](https://github.com/orgs/community/discussions/154148)
- [Best practices for Projects — docs.github.com](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/best-practices-for-projects)
