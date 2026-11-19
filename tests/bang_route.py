"""
tests/bang_route.py — bảng (method, path) của Brain, MỘT chỗ cho mọi test cần nó (#30).

VÌ SAO KHÔNG DUYỆT `app.routes`
-------------------------------
Từ FastAPI 0.162, `include_router` gói route vào `_IncludedRouter` thay vì trải ra
`app.routes`. Đo 20/11/2026 trên app này:

  | FastAPI | duyệt phẳng `app.routes` | `app.openapi()["paths"]` |
  |---------|--------------------------|--------------------------|
  | 0.136.3 | 24 cặp                   | 24 cặp, giống từng phần tử |
  | 0.165.0 | **0** cặp                | 24 cặp, giống từng phần tử |

(24 = không tính các đường cố ý mở như `/health`.) Đi đệ quy xuống `_IncludedRouter`
thì phải đọc `original_router` / `include_context`: thuộc tính của một lớp có gạch
dưới, đổi tên lúc nào cũng được. `openapi()` là API công khai, nên lấy từ đó.

CÁI GIÁ: route khai `include_in_schema=False` không có trong `openapi()`, tức sẽ lọt
khỏi bộ kiểm token. `test_auth_bao_phu.py::test_khong_route_nao_an_khoi_openapi` chặn
đúng chỗ đó.

Hai test dùng file này từng có hai vòng duyệt phẳng riêng (`test_auth_bao_phu.py`,
`test_body_contract.py`), nên nâng FastAPI làm hỏng cả hai cùng lúc (R4).
"""

from __future__ import annotations

from fastapi import FastAPI

# Khoá cấp path trong OpenAPI còn có thể là `parameters`, `summary`... — chỉ lấy method.
_METHOD = {"get", "post", "put", "patch", "delete"}


def bang_route(app: FastAPI) -> list[tuple[str, str]]:
    """Mọi cặp (METHOD, path) app phục vụ, sắp xếp, path giữ nguyên `{tham_so}`."""
    paths = app.openapi().get("paths", {})
    return sorted(
        (method.upper(), path)
        for path, ops in paths.items()
        for method in ops
        if method in _METHOD
    )
