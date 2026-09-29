"""
run_extract_local.py
Script trích xuất nội dung file XLSX có n sheet và bảng phức tạp (merged cells).
HOÀN TOÀN KHÔNG DÙNG LLM - CHẠY THUẦN PYTHON LOCAL.
"""

import json
import os
import sys
from typing import Any
import openpyxl


def unmerge_and_fill_cells(sheet) -> None:
    """Xử lý các ô gộp (merged cells): sao chép giá trị ô đầu cho toàn bộ vùng merge

    để giữ nguyên ngữ cảnh phân loại/danh mục của bảng câu hỏi kiểm toán.
    """
    merged_ranges = list(sheet.merged_cells.ranges)
    for rng in merged_ranges:
        min_col, min_row, max_col, max_row = (
            rng.min_col,
            rng.min_row,
            rng.max_col,
            rng.max_row,
        )
        top_left_value = sheet.cell(row=min_row, column=min_col).value
        sheet.unmerge_cells(str(rng))
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                sheet.cell(row=row, column=col).value = top_left_value


def extract_xlsx_raw(file_path: str) -> dict[str, Any]:
    """Trích xuất chi tiết từng sheet từ file .xlsx mà không gọi LLM."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Không tìm thấy file tại đường dẫn: {file_path}")

    wb = openpyxl.load_workbook(file_path, data_only=True)
    result = {
        "source_file": file_path,
        "sheets_count": len(wb.sheetnames),
        "sheets": {},
    }

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]

        # 1. Chuẩn hoá các ô gộp dòng/cột
        unmerge_and_fill_cells(sheet)

        rows_raw = list(sheet.iter_rows(values_only=True))
        if not rows_raw:
            result["sheets"][sheet_name] = {"type": "empty", "data": []}
            continue

        # 2. Tìm dòng bắt đầu có dữ liệu
        start_idx = 0
        while start_idx < len(rows_raw) and all(
            c is None for c in rows_raw[start_idx]
        ):
            start_idx += 1

        if start_idx >= len(rows_raw):
            result["sheets"][sheet_name] = {"type": "empty", "data": []}
            continue

        # 3. Đánh giá sheet là dạng văn bản/hướng dẫn hay bảng dữ liệu
        max_non_empty_cols = max(
            len([c for c in r if c is not None]) for r in rows_raw[start_idx:]
        )

        if max_non_empty_cols <= 2:
            # Sheet ghi chú / hướng dẫn / metadata dạng key-value
            text_lines = []
            for r in rows_raw[start_idx:]:
                items = [
                    str(c).strip() for c in r if c is not None and str(c).strip()
                ]
                if items:
                    text_lines.append(": ".join(items))
            result["sheets"][sheet_name] = {
                "type": "text_or_metadata",
                "content": text_lines,
            }
        else:
            # Sheet dạng bảng biểu kiểm toán (nhiều cột)
            header_row = rows_raw[start_idx]
            header = [
                str(c).strip() if c is not None else f"col_{i+1}"
                for i, c in enumerate(header_row)
            ]

            rows_data = []
            for raw_row in rows_raw[start_idx + 1 :]:
                if all(c is None or str(c).strip() == "" for c in raw_row):
                    continue
                row_dict = {}
                for i, cell in enumerate(raw_row):
                    col_name = (
                        header[i] if i < len(header) else f"col_{i+1}"
                    )
                    # Giữ nguyên giá trị thô, ô trống để giá trị rỗng
                    row_dict[col_name] = (
                        "" if cell is None else str(cell).strip()
                    )
                rows_data.append(row_dict)

            result["sheets"][sheet_name] = {
                "type": "table",
                "columns": header,
                "total_rows": len(rows_data),
                "rows": rows_data,
            }

    return result


if __name__ == "__main__":
    # Đường dẫn file đầu vào
    input_file = (
        r"D:\PHUOC\RAI_LLM\rikai_prototype2\rikai_prototype\data\input\xlsx_data_llm.xlsx"
    )

    print(f"=== Đang trích xuất file: {input_file} (Chế độ: NO LLM) ===")
    try:
        extracted = extract_xlsx_raw(input_file)

        # Xuất ra file JSON để kiểm tra
        output_json = "extracted_result.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        print(f"✓ Trích xuất thành công {extracted['sheets_count']} sheet.")
        for name, content in extracted["sheets"].items():
            sheet_type = content.get("type")
            if sheet_type == "table":
                print(
                    f"  - Sheet '{name}': [Bảng] {len(content['columns'])} cột, {content['total_rows']} dòng"
                )
            elif sheet_type == "text_or_metadata":
                print(
                    f"  - Sheet '{name}': [Text/Meta] {len(content['content'])} mục"
                )
            else:
                print(f"  - Sheet '{name}': Trống")

        print(f"✓ Dữ liệu trích xuất chi tiết đã lưu tại: {output_json}")

    except Exception as err:
        print(f"✗ Lỗi khi xử lý file: {err}")