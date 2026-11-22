"""
src/api/routes/documents.py — Upload (caption) & OCR (hóa đơn) endpoints.

Vision = một model thị giác duy nhất, VISION_MODEL_ID (qua ModelEngine). Đã bỏ Florence-2 và mọi
tham chiếu liên quan. /ocr áp dụng nguyên tắc deterministic-first: số tiền
do VLM trích xuất PHẢI được MCPServer tính lại bằng code thuần trước khi tin.
"""
import logging
import os
import re
import tempfile
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from src.api.dependencies import MAX_UPLOAD_BYTES, require_api_token, runtime
from src.core.config import Config
from src.core.freight_invoice import FreightInvoice
from src.core.freight_invoice import verify as verify_freight
from src.core.mcp_server import MCPServer
from src.core.sanitize import lam_sach_cay, lam_sach_chuoi, lam_sach_raw
from src.core.schemas import InvoicePayload
from src.core.utils import loai_loi

logger = logging.getLogger("projecta.api.documents")


def _log_loi_luoc_do(ten: str, exc: Exception) -> None:
    """Ghi lại việc VLM trả dữ liệu không qua lược đồ, mà KHÔNG chép nội dung.

    Thông báo của pydantic kèm theo GIÁ TRỊ đầu vào (tên nhà xe, mã số thuế, số
    tiền trên hoá đơn), và log cũng là một nơi dữ liệu khách nằm lại. Nên chỉ ghi
    loại lỗi và số lỗi — đủ để biết tỷ lệ VLM trả sai hình dạng, không đủ để dựng
    lại hoá đơn.
    """
    dem = exc.error_count() if hasattr(exc, "error_count") else None
    logger.warning(
        "VLM trả dữ liệu không qua lược đồ %s (%s, %s lỗi)", ten, type(exc).__name__, dem
    )
router = APIRouter()


def _lam_sach_ket_qua_vlm(extracted: dict) -> tuple[dict, str, list[dict]]:
    """
    Làm sạch MỌI chuỗi mà model thị giác đọc ra từ ảnh, TRƯỚC khi nó chạm lược đồ, lớp kiểm số hay
    Body (AGENTS §4.1 quy tắc 8; `src/core/sanitize.py`). Trả `(cây_sạch, raw_sạch, cờ)`.

    `raw` (đầu ra thô ở đường lỗi) tách riêng vì nhiều dòng và có trần dài hơn các trường thường.
    """
    raw_sach, co_raw = lam_sach_raw(extracted.get("raw", ""))
    sach, flags = lam_sach_cay({k: v for k, v in extracted.items() if k != "raw"})
    if co_raw:
        flags.append({"field": "raw", "reasons": list(co_raw)})
    return sach, raw_sach, flags


_TEN_TRUONG_TIEN = re.compile(r"[a-z_]{1,20}(?:\[\d{1,3}\]\.[a-z_]{1,20})?")


def _lay_loi_so_tien(extracted: dict) -> list[str]:
    """
    Tên các trường số tiền không đọc được (do `VisionAgent._doc_so_tien` đặt), lấy ra khỏi `extracted`. Chỉ nhận đúng dạng tên trường
    (`total`, `charges[0].unit_price`): chuỗi khác không đi tiếp tới người dùng.
    """
    tho = extracted.pop("so_tien_loi", None)
    if not isinstance(tho, list):
        return []
    return [t for t in tho if isinstance(t, str) and _TEN_TRUONG_TIEN.fullmatch(t)][:20]


def _kem_co(resp: dict, flags: list[dict]) -> dict:
    """
    Chuỗi trông như chỉ dẫn cho model KHÔNG bị xoá (xoá là sửa dữ liệu của khách mà không báo): nó được
    giữ và đi kèm cờ. Có cờ thì buộc `needs_manual_review`. Không có cờ thì phản hồi y nguyên như trước.
    """
    if flags:
        resp["content_flags"] = flags
        if resp.get("success") or resp.get("status") == "success":
            resp["needs_manual_review"] = True
    return resp


def _loi_an_toan(exc: Exception) -> str:
    """`str(exc)` có thể chép lại nội dung model sinh (lỗi JSON, lỗi pydantic): làm sạch trước khi trả Body."""
    return lam_sach_chuoi(str(exc), nhieu_dong=True)[0]


def _vision_backend() -> str:
    """
    Tên model vision ĐANG chạy, đọc từ config chứ không ghi cứng.

    Bốn chỗ trong file này từng ghi cứng "qwen2-vl-2b". Đổi model (03/08/2026:
    lên Qwen2.5-VL-3B) là nhãn thành sai — mà nhãn này chính là thứ dùng để so
    kết quả OCR giữa hai lần chạy. Nhãn sai thì không lần ra được con số nào do
    model nào đọc.
    """
    return Config().vision_model_id


def _safe_unlink(path: str) -> None:
    """Xoá file tạm. Thất bại thì KHÔNG ném, nhưng phải nói ra.

    `except OSError: pass` trần không vi phạm nguyên văn AGENTS §4.1 quy tắc 4
    (điều luật nêu `except Exception: pass`), nhưng hậu quả thì có thật: file
    tạm xoá không được sẽ tích lại trên đĩa, và ở bậc T0/T1 — GPU thuê, đĩa
    nhỏ — đĩa đầy làm cả service chết mà không có dòng log nào dẫn về đây.
    """
    try:
        os.unlink(path)
    except OSError as loi:
        logger.warning("Không xoá được file tạm %s: %s", path, loi)


async def _read_upload_to_tmp(request: Request, file: UploadFile) -> str:
    content_length = int(request.headers.get("content-length") or "0")
    if content_length > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file received")
    suffix = os.path.splitext(file.filename or ".png")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    return tmp.name


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    x_api_token: Optional[str] = Header(None),
):
    """Vai trò 1: caption ảnh (mô tả chi tiết)."""
    require_api_token(x_api_token)
    await runtime.ensure_vision_runtime()
    if not runtime.vision:
        raise HTTPException(status_code=503, detail="Vision runtime unavailable")

    path = await _read_upload_to_tmp(request, file)
    try:
        caption = await runtime.vision.analyze_image(path, task_hint="caption")
        caption, co = lam_sach_raw(caption)
        flags = [{"field": "vision_analysis", "reasons": list(co)}] if co else []
        return _kem_co(
            {"status": "success", "backend": _vision_backend(), "vision_analysis": caption}, flags
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Upload endpoint failed: %s", loai_loi())
        return {"status": "error", "error": _loi_an_toan(exc)}
    finally:
        _safe_unlink(path)


@router.post("/ocr")
async def ocr_endpoint(
    request: Request,
    file: UploadFile = File(...),
    x_api_token: Optional[str] = Header(None),
):
    """
    Vai trò 2: OCR hóa đơn -> JSON có cấu trúc, rồi VALIDATE bằng MCPServer.
    Không bước nào để số liệu VLM đi thẳng ra ngoài mà chưa tính lại.
    """
    require_api_token(x_api_token)
    await runtime.ensure_vision_runtime()
    if not runtime.vision:
        raise HTTPException(status_code=503, detail="Vision runtime unavailable")

    path = await _read_upload_to_tmp(request, file)
    try:
        extracted = await runtime.vision.extract_invoice(path)
        extracted, raw, flags = _lam_sach_ket_qua_vlm(extracted)
        if "error" in extracted:
            return _kem_co({
                "success": False,
                "backend": _vision_backend(),
                "error": extracted["error"],
                "raw": raw,
            }, flags)

        loi_tien = _lay_loi_so_tien(extracted)

        # 1) Ép schema (bắt JSON sai cấu trúc ngay)
        try:
            invoice = InvoicePayload(**extracted)
        except Exception as exc:
            _log_loi_luoc_do("InvoicePayload", exc)
            return _kem_co({
                "success": False,
                "backend": _vision_backend(),
                "error": f"schema_invalid: {_loi_an_toan(exc)}",
                "raw_json": extracted,
                **({"so_tien_khong_doc_duoc": loi_tien} if loi_tien else {}),
            }, flags)

        # 2) DETERMINISTIC-FIRST: tính lại tổng bằng code thuần (MCPServer)
        items = [it.model_dump() for it in invoice.items]
        validation = MCPServer.validate_invoice_total(items, invoice.total)

        return _kem_co({
            "success": True,
            "backend": _vision_backend(),
            "invoice": invoice.model_dump(),
            "validation": validation,                 # is_valid / calculated_total / difference
            # Số tiền nào model chép mà mã không đọc được thành số (BR-19 2b) thì phải người xem, dù phần còn lại cân đối.
            "needs_manual_review": not validation["is_valid"] or bool(loi_tien),
            **({"so_tien_khong_doc_duoc": loi_tien} if loi_tien else {}),
        }, flags)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OCR endpoint failed: %s", loai_loi())
        return {"success": False, "error": _loi_an_toan(exc)}
    finally:
        _safe_unlink(path)


@router.post("/ocr/freight")
async def ocr_freight_endpoint(
    request: Request,
    file: UploadFile = File(...),
    x_api_token: Optional[str] = Header(None),
):
    """
    Đọc HOÁ ĐƠN CƯỚC VẬN TẢI của nhà xe -> JSON + kiểm số học.

    Đường RIÊNG, không thay `/ocr`. Công ty vừa phân phối dầu nhớt (nhập hàng ->
    hoá đơn bán lẻ, `InvoicePayload`) vừa làm vận tải (thuê nhà xe -> hoá đơn
    cước, `FreightInvoice`). Hai loại chứng từ khác hình dạng hẳn nhau: hoá đơn
    cước có tuyến, loại xe, biển số, số chuyến, và phụ phí đứng riêng. Nhét
    chung một lược đồ là mất khả năng đối chiếu với sổ chuyến.

    Khác `/ocr` ở hai chỗ:
      - có RÀNG BUỘC giải mã theo lược đồ (đường bán lẻ sinh tự do rồi vá cú
        pháp — mà vá cú pháp không dựng lại được trường thiếu),
      - lớp kiểm tính lại cộng tiền hàng, tiền thuế VÀ tổng cộng, chứ không chỉ
        tổng.
    """
    require_api_token(x_api_token)
    await runtime.ensure_vision_runtime()
    if not runtime.vision:
        raise HTTPException(status_code=503, detail="Vision runtime unavailable")

    path = await _read_upload_to_tmp(request, file)
    try:
        extracted = await runtime.vision.extract_freight_invoice(path)
        extracted, raw, flags = _lam_sach_ket_qua_vlm(extracted)
        if "error" in extracted:
            return _kem_co({"success": False, "backend": _vision_backend(),
                            "error": extracted["error"], "raw": raw}, flags)

        loi_tien = _lay_loi_so_tien(extracted)
        try:
            invoice = FreightInvoice(**extracted)
        except Exception as exc:
            _log_loi_luoc_do("FreightInvoice", exc)
            return _kem_co({"success": False, "backend": _vision_backend(),
                            "error": f"schema_invalid: {_loi_an_toan(exc)}",
                            "raw_json": extracted,
                            **({"so_tien_khong_doc_duoc": loi_tien} if loi_tien else {})}, flags)

        # TẤT ĐỊNH TRƯỚC: VLM chỉ đọc chữ, mọi phép cộng nhân tính lại bằng code.
        check = verify_freight(invoice)
        if loi_tien:
            # Trường đó đã thành `None` (chưa đọc được), KHÔNG phải số đoán; `verify` có thể vẫn nói khớp trên phần còn lại, nên nói thẳng ở đây.
            check["ok"] = False
            check["issues"].append(
                "Số tiền chép từ tờ in không đọc được thành số ở: " + ", ".join(loi_tien)
                + " (không theo cách viết số Việt Nam). Cần người xem lại."
            )

        return _kem_co({
            "success": True,
            "backend": _vision_backend(),
            "invoice": invoice.model_dump(),
            "validation": check,
            # Sai mà biết mình sai thì còn dùng được. `ok` đòi cả "không lệch"
            # lẫn "đã thật sự kiểm được" — ảnh mờ đọc ra rỗng KHÔNG được coi là
            # một tờ hoá đơn sạch.
            "needs_manual_review": not check["ok"],
        }, flags)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OCR freight endpoint failed: %s", loai_loi())
        return {"success": False, "error": _loi_an_toan(exc)}
    finally:
        _safe_unlink(path)
