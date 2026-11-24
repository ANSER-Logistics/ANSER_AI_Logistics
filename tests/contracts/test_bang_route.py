"""Bảng route phải giữ mọi phương thức, kể cả khi có metadata cùng cấp."""

from fastapi import FastAPI

from tests.support.bang_route import bang_route


def test_cac_phuong_thuc_openapi_va_metadata(monkeypatch):
    app = FastAPI()
    methods = ["GET", "HEAD", "OPTIONS", "TRACE", "PUT", "PATCH", "POST", "DELETE"]

    def sample():
        return {}

    for method in methods:
        app.add_api_route("/sample", sample, methods=[method])
    schema = app.openapi()
    schema["paths"]["/sample"]["parameters"] = []
    monkeypatch.setattr(app, "openapi", lambda: schema)
    assert bang_route(app) == sorted((method, "/sample") for method in methods)
