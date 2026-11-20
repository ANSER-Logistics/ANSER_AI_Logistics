"""
`offline_training/cham_lai_n8n.py` phải chấm bằng CÙNG catalog node với `benchmark_v3` (#175).

Lần chạy đầu ngày 20/11 bỏ bước nạp catalog: `validate_workflow` rơi về catalog dự phòng 12 node, nên mọi workflow
dùng `respondToWebhook` bị chấm hỏng oan (v3 ra 32/34 "cách cũ" trong khi benchmark đo 33/34 trên đúng đầu ra đó).
"""

from __future__ import annotations

import json
import os

import pytest

from offline_training import cham_lai_n8n, make_n8n_pairs
from src.core import workflow_schema


@pytest.fixture
def catalog_sach(monkeypatch, tmp_path):
    monkeypatch.setattr(make_n8n_pairs, "GENERATED_DIR", tmp_path)   # _catalog/ ghi vào thư mục tạm
    cu = os.environ.pop("N8N_TEMPLATES_DIR", None)
    workflow_schema.reload_catalog()
    yield tmp_path
    # `_stage_catalog_dir()` gán thẳng `os.environ` (không qua monkeypatch), nên phải trả lại biến TRƯỚC khi nạp lại
    # catalog; để sót thì test sau (`test_training_pipeline_v3`, so dấu vân tay catalog) thấy catalog của thư mục tạm.
    if cu is None:
        os.environ.pop("N8N_TEMPLATES_DIR", None)
    else:
        os.environ["N8N_TEMPLATES_DIR"] = cu
    workflow_schema.reload_catalog()


def test_catalog_du_phong_thieu_respond_to_webhook(catalog_sach):
    # Tiền đề của lỗi: không nạp catalog thì node này bị cấm.
    assert "n8n-nodes-base.respondToWebhook" not in workflow_schema.allowed_types()


def test_main_nap_catalog_nhu_benchmark(catalog_sach):
    tho = catalog_sach / "v_tho.jsonl"
    tho.write_text(json.dumps({"nhanh": "n8n", "_id": "ca1", "finish": "stop", "output": "{}"}) + "\n",
                   encoding="utf-8")
    assert cham_lai_n8n.main([str(tho)]) == 0
    assert "n8n-nodes-base.respondToWebhook" in workflow_schema.allowed_types(), (
        "cham_lai_n8n phải nạp catalog workflow mẫu thật như benchmark_v3, không dùng catalog dự phòng"
    )
