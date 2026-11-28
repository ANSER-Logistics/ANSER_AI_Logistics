<!--
Base phải là `feat/workflow-format-and-deterministic-core`, KHÔNG phải `main` (AGENTS.md §6.0).
Kiểm: gh pr view <N> --json baseRefName -q .baseRefName
Mở draft khi chưa qua pytest + ruff + mypy hoặc đang chờ phản biện.
Khoá HMAC, token, mật khẩu: không dán vào đây.
-->

## Tóm tắt

<!-- Việc gì, vì sao. Một đến ba câu. -->

Closes #
<!-- `Closes #N` khi xong hẳn, `Refs #N` khi mới một phần. Lưu ý: PR vào nhánh không phải default
không tự đóng issue, nên đóng tay sau khi gộp. -->

## Thay đổi

<!-- Tệp hoặc hành vi nào đổi. Bảng cũng được. -->

## Kiểm tra (dán kết quả thật, đỏ thì nói đỏ)

```
ENV=LOCAL pytest -q
ruff check src tests offline_training launch_demo.py execute_backup_and_push.py
mypy src offline_training
```

## Định nghĩa xong (AGENTS.md §7, đủ cả 7)

- [ ] Chạy được ở `ENV=LOCAL`, không cần GPU
- [ ] Không vi phạm R1–R5
- [ ] Có test cho phần logic tất định; kết quả `pytest` ở trên
- [ ] Tài liệu bị ảnh hưởng đã cập nhật ở `anser-brain-docs`: PR đồng hành #<!-- số PR, hoặc ghi "không đổi hành vi" -->
- [ ] Chỉ số cải thiện và cách đo: <!-- ghi ở đây -->
- [ ] Chi phí vận hành thay đổi: <!-- ví dụ 0 đồng/tháng -->
- [ ] `[PASSED BY MENTOR]` <!-- người duyệt ghi khi đã soát R1 và R2 -->

## Metadata (§5.4)

Một nhãn, assignee là người mở, Priority, Effort, Project `Brain — Giao viec`, Status.
