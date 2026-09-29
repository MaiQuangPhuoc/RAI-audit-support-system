"""
Bóc tách nội dung từ XLSX mà không làm thay đổi dữ liệu gốc.

Nguyên tắc:
- Không dùng LLM ở bước này.
- Giữ nguyên giá trị cell.
- Merged cell theo chiều ngang được coi là một cột logic.
- Sau khi xác định header của một bảng, chỉ các cột thuộc header mới được
  đưa vào bảng.
- Cell nằm ngoài vùng cột của bảng (ví dụ cột E trong sheet ②基本情報)
  được giữ lại như text/instruction, không biến thành một column giả.
- Một dòng có dữ liệu ở cột của bảng vẫn là dòng bảng dù chỉ có 1 cell có
  giá trị (ví dụ dòng "備考").
"""

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def _build_merge_value_map(sheet) -> dict[tuple[int, int], tuple[str, int]]:
    """
    Map physical cells trong vùng merge về (giá trị, cột logic của ô góc
    trên-trái).

    Ví dụ B1:C1 = "内容" -> B1 và C1 đều được map về logical column B.
    Với merge theo chiều dọc, giá trị được giữ cho từng row để không mất
    thông tin khi chuẩn hóa thành table rows.
    """
    merge_map: dict[tuple[int, int], tuple[str, int]] = {}

    for merged_range in sheet.merged_cells.ranges:
        top_value = sheet.cell(
            row=merged_range.min_row,
            column=merged_range.min_col,
        ).value

        if top_value is None or str(top_value).strip() == "":
            continue

        value = str(top_value).strip()
        anchor_col = merged_range.min_col

        for r in range(merged_range.min_row, merged_range.max_row + 1):
            for c in range(merged_range.min_col, merged_range.max_col + 1):
                merge_map[(r, c)] = (value, anchor_col)

    return merge_map


def _read_rows_with_position(
    sheet,
    merge_map: dict[tuple[int, int], tuple[str, int]],
) -> list[list[tuple[int, str]]]:
    """Đọc từng row thành [(logical_column, value), ...]."""
    rows: list[list[tuple[int, str]]] = []

    for row in sheet.iter_rows():
        row_map: dict[int, str] = {}

        for cell in row:
            val = cell.value
            logical_col = cell.column

            merged = merge_map.get((cell.row, cell.column))
            if merged is not None:
                val, logical_col = merged

            if val is not None and str(val).strip() != "":
                # Nếu nhiều physical cells cùng thuộc một merged range,
                # chúng cùng ghi vào một logical column -> không tạo cột kép.
                row_map[logical_col] = str(val).strip()

        rows.append(sorted(row_map.items()))

    return rows


def _group_rows_into_blocks(rows: list[list[tuple[int, str]]]) -> list[tuple[str, object]]:
    """
    Gom rows thành text/table blocks mà không để instruction bên ngoài bảng
    trở thành column của bảng.

    Cách xác định:
    1. Row đầu tiên có >= 2 logical cells được dùng làm header của table.
    2. Sau khi table mở, các row có ít nhất một cell nằm trong header columns
       tiếp tục là table rows, kể cả row chỉ có 1 cell (ví dụ "備考").
    3. Cell nằm ngoài header columns trong cùng row được giữ thành extra text.
       Ví dụ E3/E8/E9/E10 của sheet ②基本情報.
    4. Row không có cell nào thuộc table columns sẽ kết thúc table và được
       xử lý như text.
    5. Row rỗng kết thúc table.
    """
    blocks: list[tuple[str, object]] = []
    current_rows: list[list[tuple[int, str]]] = []
    current_header_positions: list[int] = []
    current_extra_texts: list[str] = []

    def flush_table() -> None:
        nonlocal current_rows, current_header_positions, current_extra_texts
        if current_rows:
            blocks.append(
                (
                    "table",
                    {
                        "rows": current_rows.copy(),
                        "header_positions": current_header_positions.copy(),
                        "extra_texts": current_extra_texts.copy(),
                    },
                )
            )
        current_rows = []
        current_header_positions = []
        current_extra_texts = []

    for cells in rows:
        if not cells:
            flush_table()
            continue

        # Chưa có table: một row >= 2 cells khác giá trị có thể là header.
        if not current_rows:
            distinct_values = {value for _, value in cells}
            if len(cells) >= 2 and len(distinct_values) >= 2:
                current_rows = [cells.copy()]
                current_header_positions = [col for col, _ in cells]
                continue

            # Row đơn -> text.
            blocks.append(("text", [cells[0][1]]))
            continue

        header_set = set(current_header_positions)
        inside = [(col, value) for col, value in cells if col in header_set]
        outside = [value for col, value in cells if col not in header_set]

        if inside:
            # Chỉ đưa cell thuộc table columns vào table.
            current_rows.append(inside)
            current_extra_texts.extend(value for value in outside if value.strip())
        else:
            # Không còn dữ liệu thuộc table -> table kết thúc.
            flush_table()
            blocks.append(("text", [cells[0][1]]))

    flush_table()
    return blocks


def _render_text_block(block) -> str:
    return block[0]


def _render_table_block(block_data: dict) -> str:
    block = block_data["rows"]
    header_positions = block_data["header_positions"]

    if not block or not header_positions:
        return ""

    header_map = dict(block[0])
    columns = [header_map.get(c) or get_column_letter(c) for c in header_positions]

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]

    for row in block[1:]:
        row_map = dict(row)
        lines.append(
            "| " + " | ".join(row_map.get(c, "") for c in header_positions) + " |"
        )

    return "\n".join(lines)


def _extract_extra_texts(block_data: dict) -> list[str]:
    """Text nằm ngoài vùng table, ví dụ instruction ở cột E."""
    return block_data["extra_texts"]


def extract_text(file_path: str) -> str:
    workbook = load_workbook(file_path, data_only=True)
    output_parts: list[str] = []

    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        merge_map = _build_merge_value_map(sheet)

        output_parts.append(f"## Sheet: {sheet_name}")

        rows = _read_rows_with_position(sheet, merge_map)
        blocks = _group_rows_into_blocks(rows)

        for block_type, block_data in blocks:
            if block_type == "text":
                output_parts.append(_render_text_block(block_data))
                continue

            rendered = _render_table_block(block_data)
            if rendered:
                output_parts.append(rendered)

            output_parts.extend(_extract_extra_texts(block_data))

    return "\n\n".join(output_parts)


def extract_structured(file_path: str) -> list:
    """
    Bóc tách trực tiếp thành list[SheetTable], không qua LLM.

    Mỗi table block tạo thành một SheetTable.
    Các text/instruction nằm ngoài vùng column của table được đưa vào notes,
    không tạo column mới.
    """
    from core.schemas import SheetTable

    workbook = load_workbook(file_path, data_only=True)
    tables = []

    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        merge_map = _build_merge_value_map(sheet)
        rows = _read_rows_with_position(sheet, merge_map)
        blocks = _group_rows_into_blocks(rows)

        pending_notes: list[str] = []
        table_count = 0

        for block_type, block_data in blocks:
            if block_type == "text":
                pending_notes.append(_render_text_block(block_data))
                continue

            table_count += 1
            block = block_data["rows"]
            col_positions = block_data["header_positions"]
            header_map = dict(block[0])
            columns = [
                header_map.get(c) or get_column_letter(c)
                for c in col_positions
            ]

            data_rows = []
            for row in block[1:]:
                row_map = dict(row)
                data_rows.append(
                    {
                        columns[i]: row_map.get(pos, "")
                        for i, pos in enumerate(col_positions)
                    }
                )

            notes_parts = pending_notes + _extract_extra_texts(block_data)
            notes = "\n".join(x for x in notes_parts if x.strip()).strip()

            table_sheet_name = (
                sheet_name if table_count == 1 else f"{sheet_name} ({table_count})"
            )

            tables.append(
                SheetTable(
                    sheet_name=table_sheet_name,
                    notes=notes,
                    columns=columns,
                    rows=data_rows,
                )
            )
            pending_notes = []

        if pending_notes:
            trailing = "\n".join(pending_notes).strip()
            if tables and tables[-1].sheet_name.startswith(sheet_name):
                tables[-1].notes = (
                    (tables[-1].notes + "\n" + trailing).strip()
                    if tables[-1].notes
                    else trailing
                )
            else:
                tables.append(
                    SheetTable(
                        sheet_name=sheet_name,
                        notes=trailing,
                        columns=[],
                        rows=[],
                    )
                )

    return tables


if __name__ == "__main__":
    import os

    # ==============================
    # Input / Output
    # ==============================

    input_path = r"D:\PHUOC\RAI_LLM\rikai_prototype2\rikai_prototype\data\input\xlsx_data_llm.xlsx"

    output_path = r"D:\PHUOC\RAI_LLM\rikai_prototype2\rikai_prototype\data\extract\result_xlsx_data_llm.md"

    # ==============================
    # Validate input
    # ==============================

    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"Không tìm thấy file input:\n{input_path}"
        )

    # Tạo thư mục output nếu chưa có
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ==============================
    # Extract
    # ==============================

    content = extract_text(input_path)

    # ==============================
    # Save result
    # ==============================

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("========================================")
    print("XLSX extraction completed")
    print(f"Input : {input_path}")
    print(f"Output: {output_path}")
    print("========================================")