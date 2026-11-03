# docs/de-xuat-body/ — đề xuất Brain gửi sang Body

AGENTS.md §1: Brain **không được sửa** repo Body, chỉ được *đề xuất bằng văn bản*.
Thư mục này giữ phần "văn bản" đó ở dạng dùng lại được.

| File | Dùng làm gì |
|---|---|
| `../DE_XUAT_BODY_01.md` | Lý lẽ đầy đủ — dành cho người muốn hiểu vì sao |
| `../VIET-CHO-AI-DOC.md` | **Luật viết.** Đọc trước khi soạn bất cứ thứ gì gửi sang Body |

> `01-issue-body.md` đã xoá 04/11/2026. Nó là bản nháp cho một issue, nhưng việc đó cuối cùng đi bằng PR #22 — nên bản nháp thành bản sao thứ hai của cùng một nội dung, và bản sao thứ hai là bản không ai nhớ cập nhật. Nội dung sống ở chính PR. Lấy lại bằng `git show 1747a8f:docs/de-xuat-body/01-issue-body.md`.

## Mở issue thế nào

Cả hai repo giờ cùng org `ANSER-Logistics`, nên issue bên Body **liên kết được** với issue bên Brain bằng sub-issue — thứ trước khi có org không làm được.

**Cách một — có `gh`, một lệnh.**

> ⚠️ Bản trước của file này viết lệnh nhiều dòng nối bằng `\`. Đó là cú pháp
> **bash**; PowerShell không hiểu và báo
> `ParserError: ParentContainsErrorRecordException`. Lệnh dưới đây viết **một
> dòng**, chạy được ở cả hai shell. (AGENTS.md §3.2: không phụ thuộc lệnh bash.)

```
gh issue create --repo ANSER-Logistics/ANSER-logistics-body --title "Panel lợi nhuận hiện 0% khi phủ giá vốn là 'không đo được' (?? 0)" --body-file docs/de-xuat-body/01-issue-body.md
```

**Chuẩn bị `gh` — một lần:**

```powershell
winget install GitHub.cli
```

Cài xong mà gõ `gh` vẫn báo *"not recognized"* thì **PATH của cửa sổ đang mở chưa được nạp lại** — không phải cài hỏng. `winget` báo *"Found an existing package already installed"* là dấu hiệu đúng của tình huống này. Hoặc đóng/mở lại terminal, hoặc thêm cho riêng phiên đang chạy:

```powershell
$env:Path += ";C:\Program Files\GitHub CLI"
```

Rồi đăng nhập. **Bước này phải người làm** — nó mở trình duyệt, agent chạy không tương tác nên không qua được:

```powershell
gh auth login
```

Chọn `GitHub.com` → `HTTPS` → `Login with a web browser`.

**Cách hai — không cài gì:** mở trang New issue của repo Body, dán nội dung `01-issue-body.md`.

## Vì sao không để agent tự mở

Mở issue cần một credential GitHub. AGENTS.md §R2b.3 là chỉ thị trực tiếp của chủ dự án: *"Đưa bất kỳ giá trị bảo mật nào vào env / đổi cách quản lý bí mật → HỎI Ý KIẾN chủ dự án TRƯỚC."*

Cài `gh` và `gh auth login` thì credential do chính `gh` giữ, agent chỉ gọi lệnh — không có token nào đi qua biến môi trường hay mã nguồn. Đó là cách gỡ nút này mà không phạm R2b.

## Quy ước đặt tên

`NN-issue-body.md` theo số thứ tự của bản đề xuất trong `docs/DE_XUAT_BODY_NN.md`.

---

## Đã làm gì bằng kênh này (04/11/2026)

Chủ dự án chốt: **PR tính là đề xuất** — xem AGENTS.md §1.

| | |
|---|---|
| [Body#22](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/22) | PR sửa panel: `?? 0` biến "chưa đo được" thành 0% |
| [Body#25](https://github.com/ANSER-Logistics/ANSER-logistics-body/pull/25) | PR thêm `CODEOWNERS` |
| [Brain#2](https://github.com/ANSER-Logistics/ANSER_AI_Logistics/issues/2) | S6 — issue cha |
| [Body#23](https://github.com/ANSER-Logistics/ANSER-logistics-body/issues/23) · [Body#24](https://github.com/ANSER-Logistics/ANSER-logistics-body/issues/24) | hai sub-issue con của Brain#2 |

**Sub-issue xuyên repo chạy được** — kiểm chứng rồi, không phải suy đoán:

```
gh api repos/ANSER-Logistics/ANSER_AI_Logistics/issues/2/sub_issues
```

Trả về hai issue thuộc repo Body. Trước khi hai repo vào chung org, GitHub từ chối thẳng: issue cha và con phải cùng chủ sở hữu.

**Gắn sub-issue bằng lệnh:**

```
gh api --method POST repos/OWNER/REPO-CHA/issues/SO/sub_issues -F sub_issue_id=ID
```

`sub_issue_id` là trường `id` của issue con — **số lớn**, không phải `number` (số nhỏ hiển thị trên giao diện). Lấy bằng:

```
gh api repos/OWNER/REPO-CON/issues/SO --jq .id
```

Nhầm hai số này là lỗi đầu tiên gặp phải, và API không báo gì rõ ràng.

## Một việc phải chuẩn hoá trước khi sửa file .ts của Body

`frontend/src/server/brain.ts` **đang lưu CRLF** trong git, trong khi `.gitattributes` của Body ghi `*.ts text eol=lf`. File đó được commit trước khi có quy tắc.

Hậu quả: ai sửa nó trên Windows cũng tạo ra một diff **cả file** (1722 dòng), vì git chuẩn hoá lúc commit. PR #22 tách việc này thành commit riêng (`45ec2c1`) để commit nội dung đọc được.

Gặp lại tình huống tương tự thì làm vậy: một commit `git add --renormalize <file>` riêng, rồi mới commit nội dung.

## Còn thiếu một bước, cần chủ dự án

Bảng Projects chung chưa dựng được — token `gh` thiếu scope `project`, và lệnh cấp thêm mở trình duyệt nên agent không chạy được:

```powershell
gh auth refresh -s project,read:project
gh project create --owner ANSER-Logistics --title "ANSER - Brain & Body"
```

Dựng xong thì thêm cả hai repo vào board và bật **Hierarchy view** để thấy cây sub-issue.
