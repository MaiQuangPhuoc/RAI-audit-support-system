"""
Chia HearingSheet thành các chunk NHỎ để gọi LLM riêng từng chunk, KHÔNG gộp
toàn bộ Hearing Sheet vào 1 lần gọi duy nhất.

2 tầng tách nhỏ:
1. Theo BẢNG (mỗi phần tử trong sheet.tables — đã là 1 bảng riêng biệt do
   ingestion.xlsx_extractor.extract_structured() tách sẵn, kể cả khi 1 sheet
   Excel có nhiều hơn 1 bảng tách biệt).
2. Theo LÔ DÒNG (nếu 1 bảng có quá nhiều dòng — vượt `max_rows_per_chunk`):
   cắt thành nhiều lô, MỖI LÔ đều nhắc lại đầy đủ "Cột: ..." trước danh sách
   dòng của lô đó — để LLM luôn biết từng giá trị thuộc cột nào dù đang xử
   lý 1 lô ở giữa/cuối bảng, không phải chỉ lô đầu tiên mới có tên cột.

Vì sao tách theo BẢNG (không tách xuống từng dòng riêng lẻ) ở tầng 1: AGENT_
ANALYSIS cần so sánh các dòng trong CÙNG 1 bảng để phát hiện mâu thuẫn và vấn
đề "bất thường" (lạc chủ đề) — tách nhỏ hơn nữa sẽ mất khả năng so sánh này.
Việc cắt lô ở tầng 2 chỉ áp dụng khi bảng quá lớn (bắt buộc phải đánh đổi: mất
khả năng so sánh CHÉO GIỮA CÁC LÔ, nhưng vẫn so sánh được TRONG 1 lô).

Mỗi chunk tự chứa ĐẦY ĐỦ tên cột đi kèm giá trị (format "<tên cột>: <giá
trị>") — không có giá trị nào đứng một mình thiếu tên cột.
"""
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# from dataclasses import dataclass

# from core.schemas import HearingSheet, SheetTable

# DEFAULT_MAX_ROWS_PER_CHUNK = 30


# @dataclass
# class SheetChunk:
#     sheet_name: str          # tên bảng GỐC (không kèm nhãn "phần x/y") — để
#                               # LLM trả về đúng sheet_name khớp lại table gốc
#     table: SheetTable
#     text: str                 # đã bao gồm tên sheet + ghi chú/tiêu chí + tên cột + lô dòng
#     row_offset: int = 0        # số dòng đã xử lý ở các lô TRƯỚC đó của CÙNG bảng —
#                                 # cộng vào row_index LLM trả về để khớp đúng vị trí
#                                 # dòng trong table.rows gốc (LLM chỉ đếm 0,1,2.. TRONG lô)
#     part_label: str = ""       # "(phần 2/3)" — chỉ để hiển thị debug/log, không gửi
#                                 # cho LLM dưới field sheet_name


# def _rows_to_lines(table: SheetTable, rows_batch: list[dict], part_note: str = "") -> list[str]:
#     """Render một chunk bảng; text-only được xử lý riêng trong split_into_sheet_chunks."""
#     lines = [f"\n## Sheet: {table.sheet_name}"]
#     if part_note:
#         lines.append(f"[{part_note} — vẫn là 1 phần của sheet này, KHÔNG phải sheet khác]")
#     if table.notes.strip():
#         lines.append(f"[Ghi chú/Tiêu chí của sheet này]: {table.notes}")
#     lines.append(f"Cột: {', '.join(table.columns)}")
#     for row in rows_batch:
#         row_text = " | ".join(f"{c}: {row.get(c, '')}" for c in table.columns)
#         lines.append(f"- {row_text}")
#     return lines


# def split_into_sheet_chunks(
#     sheet: HearingSheet, max_rows_per_chunk: int = DEFAULT_MAX_ROWS_PER_CHUNK
# ) -> list[SheetChunk]:
#     chunks: list[SheetChunk] = []

#     if max_rows_per_chunk < 1:
#         raise ValueError("max_rows_per_chunk phải lớn hơn hoặc bằng 1")

#     for table in sheet.tables:
#         # Quy ước từ extract_structured(): columns rỗng nghĩa là phần tử chỉ chứa text/notes,
#         # không phải bảng. Giữ toàn bộ text trong một chunk, không chia theo số dòng bảng.
#         if not table.columns:
#             lines = [f"# {sheet.title}"]
#             if sheet.notes.strip():
#                 lines.append(f"Ghi chú chung (áp dụng toàn bộ Hearing Sheet): {sheet.notes}")
#             lines.append(f"## Sheet: {table.sheet_name}")
#             if table.notes.strip():
#                 lines.append(table.notes)
#             chunks.append(SheetChunk(
#                 sheet_name=table.sheet_name,
#                 table=table,
#                 text="\n".join(lines),
#                 row_offset=0,
#                 part_label="",
#             ))
#             continue

#         rows = table.rows
#         row_batches = [rows[i:i + max_rows_per_chunk] for i in range(0, len(rows), max_rows_per_chunk)] or [[]]
#         total_parts = len(row_batches)

#         for part_idx, rows_batch in enumerate(row_batches):
#             part_note = f"Phần {part_idx + 1}/{total_parts} của sheet này (các dòng tiếp theo)" if total_parts > 1 else ""

#             lines = [f"# {sheet.title}"]
#             if sheet.notes.strip():
#                 lines.append(f"Ghi chú chung (áp dụng toàn bộ Hearing Sheet): {sheet.notes}")
#             lines.extend(_rows_to_lines(table, rows_batch, part_note))

#             chunks.append(SheetChunk(
#                 sheet_name=table.sheet_name,
#                 table=table,
#                 text="\n".join(lines),
#                 row_offset=part_idx * max_rows_per_chunk,
#                 part_label=f"(phần {part_idx + 1}/{total_parts})" if total_parts > 1 else "",
#             ))

#     return chunks


"""
Chia HearingSheet thành các chunk NHỎ để gọi LLM riêng từng chunk, KHÔNG gộp
toàn bộ Hearing Sheet vào 1 lần gọi duy nhất.

2 tầng tách nhỏ:
1. Theo BẢNG (mỗi phần tử trong sheet.tables — đã là 1 bảng riêng biệt do
   ingestion.xlsx_extractor.extract_structured() tách sẵn, kể cả khi 1 sheet
   Excel có nhiều hơn 1 bảng tách biệt).
2. Theo LÔ DÒNG (nếu 1 bảng có quá nhiều dòng — vượt `max_rows_per_chunk`):
   cắt thành nhiều lô, MỖI LÔ đều nhắc lại đầy đủ "Cột: ..." trước danh sách
   dòng của lô đó — để LLM luôn biết từng giá trị thuộc cột nào dù đang xử
   lý 1 lô ở giữa/cuối bảng, không phải chỉ lô đầu tiên mới có tên cột.

Vì sao tách theo BẢNG (không tách xuống từng dòng riêng lẻ) ở tầng 1: AGENT_
ANALYSIS cần so sánh các dòng trong CÙNG 1 bảng để phát hiện mâu thuẫn và vấn
đề "bất thường" (lạc chủ đề) — tách nhỏ hơn nữa sẽ mất khả năng so sánh này.
Việc cắt lô ở tầng 2 chỉ áp dụng khi bảng quá lớn (bắt buộc phải đánh đổi: mất
khả năng so sánh CHÉO GIỮA CÁC LÔ, nhưng vẫn so sánh được TRONG 1 lô).

Mỗi chunk tự chứa ĐẦY ĐỦ tên cột đi kèm giá trị (format "<tên cột>: <giá
trị>") — không có giá trị nào đứng một mình thiếu tên cột.
"""
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from dataclasses import dataclass

from core.schemas import HearingSheet, SheetTable

DEFAULT_MAX_ROWS_PER_CHUNK = 30


@dataclass
class SheetChunk:
    sheet_name: str          # tên bảng GỐC (không kèm nhãn "phần x/y") — để
                              # LLM trả về đúng sheet_name khớp lại table gốc
    table: SheetTable
    text: str                 # đã bao gồm tên sheet + ghi chú/tiêu chí + tên cột + lô dòng
    row_offset: int = 0        # số dòng đã xử lý ở các lô TRƯỚC đó của CÙNG bảng —
                                # cộng vào row_index LLM trả về để khớp đúng vị trí
                                # dòng trong table.rows gốc (LLM chỉ đếm 0,1,2.. TRONG lô)
    part_label: str = ""       # "(phần 2/3)" — chỉ để hiển thị debug/log, không gửi
                                # cho LLM dưới field sheet_name


def _markdown_cell(value) -> str:
    """Chuẩn hóa giá trị cho một ô Markdown, không thay đổi ý nghĩa nội dung."""
    if value is None:
        return ""
    return str(value).replace("\\r\\n", " ").replace("\\n", " ").replace("\\r", " ").replace("|", "\\\\|").strip()


def _rows_to_lines(table: SheetTable, rows_batch: list[dict], part_note: str = "") -> list[str]:
    """Render dữ liệu bảng dưới dạng Markdown: tiêu đề cột + các hàng giá trị."""
    lines = [f"\\n## Sheet: {table.sheet_name}"]
    if part_note:
        lines.append(f"[{part_note} — vẫn là 1 phần của sheet này, KHÔNG phải sheet khác]")
    if table.notes.strip():
        lines.append(f"[Ghi chú/Tiêu chí của sheet này]: {table.notes}")

    if not table.columns:
        return lines

    # Một tên cột tương ứng với một ô header; giữ nguyên thứ tự cột từ extractor.
    headers = [_markdown_cell(column) for column in table.columns]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for row in rows_batch:
        values = [_markdown_cell(row.get(column, "")) for column in table.columns]
        lines.append("| " + " | ".join(values) + " |")

    return lines


def split_into_sheet_chunks(
    sheet: HearingSheet, max_rows_per_chunk: int = DEFAULT_MAX_ROWS_PER_CHUNK
) -> list[SheetChunk]:
    chunks: list[SheetChunk] = []

    if max_rows_per_chunk < 1:
        raise ValueError("max_rows_per_chunk phải lớn hơn hoặc bằng 1")

    for table in sheet.tables:
        # Quy ước từ extract_structured(): columns rỗng nghĩa là phần tử chỉ chứa text/notes,
        # không phải bảng. Giữ toàn bộ text trong một chunk, không chia theo số dòng bảng.
        if not table.columns:
            lines = [f"# {sheet.title}"]
            if sheet.notes.strip():
                lines.append(f"Ghi chú chung (áp dụng toàn bộ Hearing Sheet): {sheet.notes}")
            lines.append(f"## Sheet: {table.sheet_name}")
            if table.notes.strip():
                lines.append(table.notes)
            chunks.append(SheetChunk(
                sheet_name=table.sheet_name,
                table=table,
                text="\n".join(lines),
                row_offset=0,
                part_label="",
            ))
            continue

        rows = table.rows
        row_batches = [rows[i:i + max_rows_per_chunk] for i in range(0, len(rows), max_rows_per_chunk)] or [[]]
        total_parts = len(row_batches)

        for part_idx, rows_batch in enumerate(row_batches):
            part_note = f"Phần {part_idx + 1}/{total_parts} của sheet này (các dòng tiếp theo)" if total_parts > 1 else ""

            lines = [f"# {sheet.title}"]
            if sheet.notes.strip():
                lines.append(f"Ghi chú chung (áp dụng toàn bộ Hearing Sheet): {sheet.notes}")
            lines.extend(_rows_to_lines(table, rows_batch, part_note))

            chunks.append(SheetChunk(
                sheet_name=table.sheet_name,
                table=table,
                text="\n".join(lines),
                row_offset=part_idx * max_rows_per_chunk,
                part_label=f"(phần {part_idx + 1}/{total_parts})" if total_parts > 1 else "",
            ))

    return chunks