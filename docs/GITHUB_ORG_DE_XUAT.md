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

1. Lập org (tên gợi ý `ANSER-Logistics`). Miễn phí, không cần thẻ.
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

> **Trạng thái 04/11/2026.** Org [`ANSER-Logistics`](https://github.com/ANSER-Logistics) đã lập (03/11 17:45). Brain đã transfer: `ANSER-Logistics/ANSER_AI_Logistics`, vẫn public. Remote cục bộ đã trỏ lại. **Bước 0–3 xong.** Body chưa transfer — bước 4 chờ Dgsonn.

Thứ tự này có lý do: mỗi bước kiểm được trước khi sang bước sau, và bước nào hỏng thì lùi lại được mà chưa ai mất việc.

### Bước 0 — trả lời câu hỏi billing trước

**Làm trước mọi thứ khác**, vì câu trả lời quyết định org đáng giá đến đâu.

Mở `github.com/settings/billing` bằng tài khoản `PCBoiz`. Đọc lý do khoá.

- Nếu là **thẻ thanh toán lỗi / hết hạn** ở cấp tài khoản → org mới có billing riêng, nhiều khả năng CI chạy lại được ngay, 0đ (repo public dùng standard runner miễn phí).
- Nếu là **tranh chấp / vi phạm điều khoản** → org cùng chủ có thể kế thừa. Hỏi GitHub Support trước khi transfer.

Ghi lại nguyên văn dòng lý do rồi báo lại — tôi không có quyền vào trang đó.

### Bước 1 — lập org (2 phút, không cần thẻ)

`github.com/organizations/plan` → **Free** → đặt tên.

- Tên đề xuất: `ANSER-Logistics`. Phải là tên chưa ai dùng trên toàn GitHub.
- "This organization belongs to": chọn **My personal account**, không phải business — business hỏi thông tin doanh nghiệp và không cần cho gói Free.
- Email liên hệ: email anh đang dùng cho GitHub.

Chưa mời ai ở bước này.

### Bước 2 — tạo hai team

`github.com/orgs/ANSER-Logistics/teams` → **New team**, làm hai lần:

| Team | Thành viên | Quyền mặc định |
|---|---|---|
| `brain` | Thành | Write |
| `body` | Sĩ, Nam, (Sơn) | Write |

Anh là **Owner** của org, không cần ở trong team nào.

Đừng đặt quyền Admin cho team. Admin cho phép xoá repo và đổi hiển thị public/private — thứ mục 3 nói là không được đổi.

### Bước 3 — transfer repo Brain

`github.com/PCBoiz/ANSER_AI_Logistics/settings` → cuối trang, **Danger Zone** → **Transfer ownership** → gõ `ANSER-Logistics`.

Trước khi bấm, chạy lại một lượt quét bí mật trên toàn bộ lịch sử (R2b.2 — transfer giữ nguyên mọi commit):

```bash
git log --all -S 'npg_' --oneline | head
git log --all -S 'postgres://' --oneline | head
git log --all -S 'sk-' --oneline | head
```

Lần quét trước mọi kết quả khớp đều là fixture của test. Hai phút, cứ quét lại.

Sau khi transfer, trên **máy của từng người**:

```bash
git remote set-url origin https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git
git remote -v        # xác nhận
```

URL cũ vẫn redirect, nhưng đừng dựa vào đó.

### Bước 4 — transfer repo Body

**Việc này chỉ Dgsonn làm được.** Anh không transfer hộ repo của người khác.

Cùng đường: `Settings` → `Danger Zone` → `Transfer ownership` → `ANSER-Logistics`.

Dgsonn cần được mời vào org trước (ít nhất quyền Member) thì mới chọn được org làm đích.

### Bước 5 — gán quyền repo cho team

Ở mỗi repo: `Settings` → `Collaborators and teams` → **Add teams**.

- `ANSER_AI_Logistics` → team `brain`: **Write**; team `body`: **Read**
- `ANSER-logistics` → team `body`: **Write**; team `brain`: **Read**

**Read cho đội kia là có chủ ý.** AGENTS.md §1 nói Brain không được sửa Body. Đến đây nó không còn là quy tắc giấy nữa — GitHub chặn thật. Nhưng vẫn đọc được, mà đọc là cần: lược đồ Body là nguồn sự thật cho `SCHEMA MAP` bên Brain.

### Bước 6 — CODEOWNERS: biến quy tắc giấy thành cổng kỹ thuật

**Vấn đề nó giải:** AGENTS.md §1 viết "Body KHÔNG ĐƯỢC SỬA, chỉ được đề xuất thay đổi bằng văn bản". Hôm nay đó là một câu trong file — ai quên là vi phạm, và không có gì chặn lại. CODEOWNERS biến nó thành thứ GitHub thi hành.

**Nó hoạt động thế nào.** Mỗi dòng là một *mẫu đường dẫn* rồi tới *ai sở hữu nó*. Khi có PR chạm vào file khớp mẫu, GitHub tự thêm người/team đó làm người duyệt bắt buộc. **Dòng khớp CUỐI CÙNG thắng** — ngược với `.gitignore`, nên thứ tự quan trọng: mẫu chung trước, mẫu cụ thể sau.

**Làm:** tạo `.github/CODEOWNERS` trong repo Brain, trên nhánh mặc định.

```
# Mặc định: mọi thứ trong Brain thuộc team brain.
*                               @ANSER-Logistics/brain

# Năm ràng buộc bất biến. Đổi chúng là đổi luật chơi của cả dự án,
# nên PR chạm vào đây luôn cần chủ dự án nhìn.
/AGENTS.md                      @ANSER-Logistics/brain @Dgsonn
/ARCHITECTURE.md                @ANSER-Logistics/brain @Dgsonn

# R4 — ba nơi phải khớp nhau. Sửa một nơi mà quên hai nơi kia là lỗi,
# và loại lỗi đó không có triệu chứng cho tới lúc sinh workflow sai.
/src/core/prompts.py            @ANSER-Logistics/brain
/src/core/agent_middleware.py   @ANSER-Logistics/brain
/src/api/routes/chat.py         @ANSER-Logistics/brain

# R1 — tầng tất định. Sai ở đây là sai sổ sách của khách.
/src/core/grounding.py          @ANSER-Logistics/brain
/src/core/mcp_server.py         @ANSER-Logistics/brain
/src/core/saas_api.py           @ANSER-Logistics/brain
```

Repo Body làm tương tự, đổi thành `@ANSER-Logistics/body`.

**Hai điều hay nhầm:**

- Team được nhắc phải có **quyền Write trở lên** trên repo đó, nếu không GitHub bỏ qua dòng ấy *mà không báo lỗi*. Đây là lý do bước 5 phải làm trước bước 6.
- File này **chưa có tác dụng gì** cho tới khi bật "Require review from Code Owners" ở bước 7. Tự nó chỉ là gợi ý người duyệt.

**Kiểm:** mở một PR nháp sửa một dòng trong `AGENTS.md`. Ô "Reviewers" phải tự điền team `brain`. Không tự điền thì sai ở quyền team hoặc sai cú pháp — GitHub có trang `Settings → Code owners` liệt kê lỗi cú pháp.

---

### Bước 7 — ruleset: ai được đẩy thẳng vào nhánh chính

**Vấn đề nó giải:** hiện `main` không có gì chặn. Một lệnh `git push` là code vào nhánh chính, không ai nhìn. Với một dự án mà sai số là sai sổ sách của khách, đó là cổng rẻ nhất chưa đóng.

Ruleset khác branch protection cũ ở chỗ nó đặt được ở cấp org cho nhiều repo cùng lúc. Lần đầu cứ làm ở cấp repo cho dễ hiểu, nâng lên org sau.

**Làm:** repo Brain → `Settings` → `Rules` → `Rulesets` → `New ruleset` → `New branch ruleset`.

| Ô | Điền | Vì sao |
|---|---|---|
| Ruleset Name | `bao-ve-main` | tên gì cũng được |
| Enforcement status | **Active** | để `Disabled` thì nó chỉ nằm đó |
| Bypass list | **để trống** | thêm chính mình vào đây là tự vô hiệu hoá cái vừa dựng |
| Target branches | `Add target` → `Include default branch` | bám nhánh mặc định, đổi tên nhánh không gãy |

Rồi tick trong phần **Rules**:

- ☑ **Require a pull request before merging**
  - Required approvals: **1**
  - ☑ **Require review from Code Owners** ← dòng này mới kích hoạt bước 6
  - ☑ **Dismiss stale pull request approvals when new commits are pushed** — duyệt xong rồi đẩy thêm commit thì lần duyệt đó không còn nói về code hiện tại nữa
- ☑ **Block force pushes** — `--force` viết đè lịch sử người khác, không khôi phục được
- ☐ **Require status checks to pass** — **CHƯA BẬT.** Bật khi CI chưa chạy được là tự khoá mình: không check nào xanh nổi thì không PR nào merge được. Quay lại bật sau bước 10.
- ☐ **Restrict deletions** — bật cũng được, rẻ.

**Đội 1–2 người thì sao?** Required approvals = 1 nghĩa là **không ai tự duyệt PR của chính mình**. Thành làm Brain một mình thì mọi PR sẽ cần anh duyệt. Vướng quá thì để `0` mà vẫn bật "Require a pull request" — vẫn chặn push thẳng, vẫn có chỗ đọc diff, chỉ không bắt buộc người thứ hai.

---

### Bước 8 — issue type và board: ghi được việc này chặn việc kia

**Vấn đề nó giải.** AGENTS.md §8 ghi S6 là "⚪ Chặn — cần phối hợp repo Body". Câu đó chỉ sống trong văn bản. Không ai mở bảng ra mà thấy *việc nào bên Brain đang đứng vì việc nào bên Body*. Đây đúng là thứ hai tài khoản cá nhân riêng lẻ không làm được, và là lý do kỹ thuật chính để lập org.

#### 8a. Issue type

`github.com/organizations/ANSER-Logistics/settings/issue-types`

Mặc định có Task / Bug / Feature. Thêm hai loại thật sự thiếu:

| Tên | Vì sao cần riêng |
|---|---|
| `R-violation` | Vi phạm một trong R1–R5. Không được để lẫn với bug thường. Bug thường là "chạy sai"; cái này là "chạy đúng nhưng vi phạm nguyên tắc nền" — ví dụ model tự tính một tỷ lệ rồi tuyên bố kết quả. Lẫn vào nhau thì nó bị xếp sau mãi mãi. |
| `blocked-cross-repo` | Việc đứng vì repo bên kia. Cho đếm được: bao nhiêu việc đang đứng, đứng bao lâu. |

Issue type là **một** giá trị mỗi issue (khác label — gắn bao nhiêu cũng được), nên nó trả lời "việc này *là loại gì*" chứ không phải "việc này *có những nhãn nào*".

#### 8b. Sub-issue — thứ chỉ org mới có

Đây là phần đáng giá nhất. Mở một issue bên Brain → cuộn xuống → **Create sub-issue** → **Add existing issue** → chọn issue **bên repo Body**.

Trước khi có org điều này **không thể làm được**: GitHub đòi issue cha và con cùng một chủ sở hữu, mà Brain thuộc `PCBoiz` còn Body thuộc `Dgsonn`. Giờ cả hai thuộc `ANSER-Logistics` nên liên kết được.

Giới hạn: 100 con mỗi cha, lồng tối đa 8 tầng.

Ví dụ cụ thể: tạo issue `S6 — API xuất dòng bán/chi phí cho /tools/report` bên Brain, rồi gắn issue `Lược đồ Logistics` bên Body làm **sub-issue**. Từ lúc đó trạng thái việc Body hiện ngay trên việc Brain.

#### 8c. Board

`github.com/orgs/ANSER-Logistics/projects` → `New project` → **Board**.

- `Settings` của project → `Manage access` → thêm cả hai team.
- Trong board: `+ Add item` → gõ `#` → chọn được issue từ **cả hai repo**.
- Bật **Hierarchy view** (ra bản chính thức 01/2026) để thấy cây sub-issue; gom, lọc, sắp xếp vẫn giữ nguyên cây.

> **Kiểm ngay ở bước này** câu hỏi còn treo ở mục 6: một board có trải được hai repo không. Tôi không tìm được tài liệu chính thức xác nhận cho 2026. Thử 10 phút rẻ hơn tranh luận — và nếu không được thì chỉ cần hai board, không ảnh hưởng bước 1–7.

Gợi ý cột: `Chờ quyết` · `Sẵn sàng` · `Đang làm` · `Chờ duyệt` · `Xong`. Cột `Chờ quyết` là cột hay thiếu nhất, mà phần lớn việc đứng là đứng ở đó.

---

### Bước 9 — dọn những thứ còn trỏ vào địa chỉ cũ

Transfer xong thì URL cũ vẫn redirect, nên mọi thứ *có vẻ* vẫn chạy. Đó là lý do bước này hay bị bỏ qua, rồi gãy vài tuần sau khi ai đó tạo lại repo trùng tên ở chỗ cũ.

**Trên máy từng người**, trong thư mục repo:

```bash
git remote -v
git remote set-url origin https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git
git remote -v
git fetch origin
```

**Công cụ gắn với repo:**

| Thứ | Kiểm thế nào | Ghi chú |
|---|---|---|
| grapuco | `grapuco status` | liên kết theo `repoId` chứ không theo tên, nhiều khả năng không gãy — nhưng kiểm |
| bảng kanzo `brain` | đang liên kết `pcboiz/anser_ai_logistics` | phải trỏ lại sang `anser-logistics/...` |
| badge CI, link trong README | tìm chuỗi `PCBoiz/` | |

**Tài liệu trong repo:** bảng tra cứu ở [`SO_TAY_NGUOI_MOI.md §1.2`](../SO_TAY_NGUOI_MOI.md) là chỗ phải đúng. Biên bản và bản phân việc trong [`docs/chu-ky-01/`](chu-ky-01/) thì **để nguyên** — đó là tài liệu lịch sử; sửa tên trong một biên bản đã ký là viết lại cái đã xảy ra.

---

### Bước 10 — gỡ khoá CI, rồi mới siết cổng

**Trạng thái đo được 04/11/2026:** repo Brain có **153 lượt chạy Actions, 0 lượt xanh**, liên tục từ 14/05/2026. Mỗi lượt chết trong 2–3 giây với **0 bước nào chạy** — job bị từ chối ngay lúc cấp phát runner, không phải test hỏng.

Nguyên nhân đã xác định: `Settings → Billing → Payment information` báo **`Invalid payment method — authorization hold failed`** (Visa …8100). Trang `Billing → Overview` hiện `$0` và không có khoản phải trả, nên nhìn ở đó sẽ tưởng không có vấn đề gì. Hai trang nói hai chuyện khác nhau; Payment information mới đúng.

**Gỡ theo thứ tự:**

1. Bấm **Retry authorization** trên banner vàng.
2. Vẫn hỏng: gọi ngân hàng, bật **thanh toán quốc tế / trực tuyến** cho thẻ. Nói rõ là "giao dịch giữ tiền xác thực từ GitHub" — thẻ nội địa Việt Nam hay chặn loại này mặc định. Rồi Retry.
3. Vẫn hỏng: đổi thẻ khác, hoặc PayPal.
4. Vẫn hỏng: mở ticket **GitHub Support → Billing**. Chỉ Support gỡ khoá thủ công được. Xem cả **Payment history** — một hoá đơn hỏng còn treo vẫn giữ cờ khoá dù thẻ đã sửa.

> Về lý, GitHub Free + repo public dùng standard runner là **miễn phí**, nên không cần thẻ nào cả. Nhưng **không có nguồn nào xác nhận** gỡ thẻ ra là hết khoá — tài liệu chính thức chỉ nói phải có một lượt authorization *thành công* thì mới tự mở. Đừng gỡ thẻ với kỳ vọng nó chữa được.

**Sau khi một lượt CI xanh**, quay lại bước 7 và bật **Require status checks to pass** → chọn job `test`. Đến lúc đó `.pre-commit-config.yaml` mới thôi là cổng duy nhất và trở thành lớp thứ hai.

Đây là lợi ích lớn nhất trong cả bản này, lớn hơn kanban: **1232 test có cổng tự động chạy lại, 0đ.**

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
