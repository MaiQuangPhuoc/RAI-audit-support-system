"""
Helper dùng chung để chuyển HearingSheet (cấu trúc cột ĐỘNG, giữ nguyên theo
file gốc Auditor — không cố định 2 cột "câu hỏi/câu trả lời") thành text
thuần đưa vào prompt LLM. Dùng chung cho cả 3 agent để không lặp code và
đảm bảo mọi agent nhìn thấy dữ liệu theo đúng 1 định dạng nhất quán.
"""

import sys , os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
from core.schemas import HearingSheet, SheetTable


def table_to_lines(table: SheetTable) -> list[str]:
    lines = [f"\n## Sheet: {table.sheet_name}"]
    if table.notes.strip():
        lines.append(f"[Ghi chú/Tiêu chí của sheet này]: {table.notes}")
    if table.columns:
        lines.append(f"Cột: {', '.join(table.columns)}")
    for row in table.rows:
        row_text = " | ".join(f"{c}: {row.get(c, '')}" for c in table.columns)
        lines.append(f"- {row_text}")
    return lines


def hearing_sheet_to_text(sheet: HearingSheet, title_suffix: str = "") -> str:
    lines = [f"# {sheet.title}{title_suffix}"]
    if sheet.notes.strip():
        lines.append(f"Ghi chú: {sheet.notes}")
    for table in sheet.tables:
        lines.extend(table_to_lines(table))
    return "\n".join(lines)