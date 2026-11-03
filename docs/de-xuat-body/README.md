# docs/de-xuat-body/ — đề xuất Brain gửi sang Body

AGENTS.md §1: Brain **không được sửa** repo Body, chỉ được *đề xuất bằng văn bản*.
Thư mục này giữ phần "văn bản" đó ở dạng dùng lại được.

| File | Dùng làm gì |
|---|---|
| `../DE_XUAT_BODY_01.md` | Lý lẽ đầy đủ — dành cho người muốn hiểu vì sao |
| `01-issue-body.md` | Bản rút gọn, dán thẳng vào issue bên repo Body |

## Mở issue thế nào

Cả hai repo giờ cùng org `ANSER-Logistics`, nên issue bên Body **liên kết được** với issue bên Brain bằng sub-issue — thứ trước khi có org không làm được.

**Cách một — có `gh`, một lệnh:**

```bash
gh issue create \
  --repo ANSER-Logistics/ANSER-logistics-body \
  --title "Panel lợi nhuận hiện 0% khi phủ giá vốn là 'không đo được' (?? 0)" \
  --body-file docs/de-xuat-body/01-issue-body.md
```

Chưa có `gh` thì: `winget install GitHub.cli` rồi `gh auth login`.

**Cách hai — không cài gì:** mở trang New issue của repo Body, dán nội dung `01-issue-body.md`.

## Vì sao không để agent tự mở

Mở issue cần một credential GitHub. AGENTS.md §R2b.3 là chỉ thị trực tiếp của chủ dự án: *"Đưa bất kỳ giá trị bảo mật nào vào env / đổi cách quản lý bí mật → HỎI Ý KIẾN chủ dự án TRƯỚC."*

Cài `gh` và `gh auth login` thì credential do chính `gh` giữ, agent chỉ gọi lệnh — không có token nào đi qua biến môi trường hay mã nguồn. Đó là cách gỡ nút này mà không phạm R2b.

## Quy ước đặt tên

`NN-issue-body.md` theo số thứ tự của bản đề xuất trong `docs/DE_XUAT_BODY_NN.md`.
