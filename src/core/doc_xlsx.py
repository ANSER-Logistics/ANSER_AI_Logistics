"""
src/core/doc_xlsx.py — MỘT chỗ mở file .xlsx và đọc dòng (R4).

Trước đây có ba bản: `inventory_import._rows_from_workbook` (gom lỗi openpyxl về `ValueError`),
còn `partner_import._rows_from_workbook` và `vat_catalog._rows` gọi thẳng `openpyxl.load_workbook`.
File hỏng, file rỗng hay tên sheet không tồn tại làm hai endpoint sau trả **500** thay vì 422
(issue #36): `BadZipFile`, `KeyError`... rơi ra ngoài vì tầng HTTP chỉ bắt `ValueError` và
`RuntimeError`. Ba bản chép tay là đúng thứ R4 cấm; bản đúng duy nhất là bản của inventory.
"""

from __future__ import annotations

from typing import Any, Optional


def doc_dong_xlsx(
    source: Any, sheet: Optional[str], *, max_rows: Optional[int] = None
) -> list[list[Any]]:
    """
    openpyxl -> list[list]. Nhận cả đường dẫn lẫn đối tượng file (BytesIO).

    Mọi lỗi do FILE (hỏng, cụt, thiếu sheet, quá dài) là `ValueError` — tầng HTTP trả 422 kèm
    lời khuyên dùng được. Thiếu thư viện là `RuntimeError` (lỗi cài đặt, không phải lỗi file).

    `max_rows` đặt thì vượt trần là LỖI chứ không cắt bớt: một bảng bị cắt cụt vẫn đọc trót
    lọt và vẫn ra kết quả kiểm, nhưng thiếu dòng, nên "không phát hiện lỗi" lại có nghĩa là
    "chưa nhìn hết". `None` = không giới hạn ở tầng đọc (người gọi tự xử).

    openpyxl là phụ thuộc tuỳ chọn — chỉ cần khi đọc Excel, nên import trong thân hàm để phần
    còn lại của module chạy được ở môi trường tối giản.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - phụ thuộc tuỳ chọn
        raise RuntimeError(
            "Cần openpyxl để đọc .xlsx:  pip install openpyxl"
        ) from exc

    # openpyxl ném đủ loại ngoại lệ cho một file hỏng (BadZipFile, KeyError,
    # xml.etree.ParseError...). Gom hết về ValueError: upload đứt giữa chừng là chuyện thường
    # ngày, không phải lỗi lập trình.
    try:
        wb = load_workbook(source, data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError(
            f"Không mở được file Excel ({type(exc).__name__}). File có thể hỏng "
            "hoặc tải lên dở chừng — thử tải lại, hoặc mở bằng Excel rồi lưu lại."
        ) from exc

    try:
        if sheet is not None and sheet not in wb.sheetnames:
            raise ValueError(
                f"Không có sheet {sheet!r}. Sheet trong file: {', '.join(wb.sheetnames)}"
            )
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows: list[list[Any]] = []
        try:
            for row in ws.iter_rows(values_only=True):
                rows.append(list(row))
                if max_rows is not None and len(rows) > max_rows:
                    raise ValueError(
                        f"File quá {max_rows:,} dòng — vượt sức một bảng tổng hợp. "
                        "Nhiều khả năng đây là bảng KÊ CHI TIẾT từng phiếu, không phải "
                        "bảng danh mục/tổng hợp."
                    )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"File Excel hỏng ở giữa chừng ({type(exc).__name__}), đọc được "
                f"{len(rows)} dòng thì dừng. Mở bằng Excel rồi lưu lại."
            ) from exc
        return rows
    finally:
        wb.close()
