"""
Lưu trữ local cho prototype:
- Lưu/đọc Hearing Sheet dạng JSON (lịch sử phiên làm việc).
- "Gửi cho Partner" = xuất Hearing Sheet ra file XLSX (2 cột: Câu hỏi/Câu trả lời)
  vào thư mục data/outbox/<partner>/.
- "Nhận từ Partner" = quét thư mục data/inbox/<partner>/ xem có file mới không.
  Đây là cách mô phỏng đơn giản cho việc gửi/nhận qua lại với Partner (thực tế
  Partner trả lời thủ công ngoài hệ thống — không thuộc phạm vi xử lý AI).

Lưu ý: việc "tự động chạy khi có file mới" theo đúng nghĩa (daemon/watcher chạy
nền) cần thư viện riêng (vd. watchdog) hoặc cron/task scheduler — ngoài phạm vi
prototype Streamlit (mô hình request-response). Ở đây dùng nút "Kiểm tra file mới"
để chủ động quét thư mục inbox mỗi khi Auditor bấm — đơn giản, đủ dùng cho demo.
"""
import glob
import json
import os
import uuid
from datetime import datetime
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)





"""
Lưu trữ local cho prototype:
- Lưu/đọc Hearing Sheet dạng JSON (lịch sử phiên làm việc).
- "Gửi cho Partner" = xuất Hearing Sheet ra file XLSX (2 cột: Câu hỏi/Câu trả lời)
  vào thư mục data/outbox/<partner>/.
- "Nhận từ Partner" = quét thư mục data/inbox/<partner>/ xem có file mới không.
  Đây là cách mô phỏng đơn giản cho việc gửi/nhận qua lại với Partner (thực tế
  Partner trả lời thủ công ngoài hệ thống — không thuộc phạm vi xử lý AI).

Lưu ý: việc "tự động chạy khi có file mới" theo đúng nghĩa (daemon/watcher chạy
nền) cần thư viện riêng (vd. watchdog) hoặc cron/task scheduler — ngoài phạm vi
prototype Streamlit (mô hình request-response). Ở đây dùng nút "Kiểm tra file mới"
để chủ động quét thư mục inbox mỗi khi Auditor bấm — đơn giản, đủ dùng cho demo.
"""
import glob
import json
import os
import uuid
from datetime import datetime

import openpyxl

import configs
from core.schemas import HearingSheet, QARow, SheetTable

OUTBOX_DIR = os.path.join(configs.DATA_DIR, "outbox")
INBOX_DIR = os.path.join(configs.DATA_DIR, "inbox")
SESSIONS_DIR = configs.SESSIONS_DIR

# data/extract: nội dung thô bóc tách từ file input, CHƯA qua LLM xử lý gì.
# data/reason: nội dung LLM suy luận/phân tích (tóm tắt cách hiểu, phân tích vấn đề)
# — lưu riêng để Auditor (hoặc dev) đối chiếu "trước/sau" khi cần debug prompt.
EXTRACT_DIR = os.path.join(configs.DATA_DIR, "extract")
REASON_DIR = os.path.join(configs.DATA_DIR, "reason")

os.makedirs(OUTBOX_DIR, exist_ok=True)
os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(EXTRACT_DIR, exist_ok=True)
os.makedirs(REASON_DIR, exist_ok=True)

# Ký tự Excel KHÔNG cho phép trong tên sheet, và giới hạn 31 ký tự.
_INVALID_SHEET_CHARS = set('[]:*?/\\')


def _safe_sheet_title(name: str, used_titles: set[str]) -> str:
    """Làm sạch tên sheet cho hợp lệ với Excel (bỏ ký tự cấm, giới hạn 31 ký tự,
    tránh trùng tên nếu 2 sheet gốc vô tình cùng tên sau khi làm sạch)."""
    cleaned = "".join(c for c in (name or "") if c not in _INVALID_SHEET_CHARS).strip()
    cleaned = (cleaned or "Sheet")[:31]
    base, i = cleaned, 2
    while cleaned in used_titles:
        suffix = f"_{i}"
        cleaned = base[: 31 - len(suffix)] + suffix
        i += 1
    used_titles.add(cleaned)
    return cleaned


def new_session_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def save_uploaded_file(file_bytes: bytes, filename: str, subfolder: str) -> str:
    folder = os.path.join(SESSIONS_DIR, subfolder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


# ---------------------------------------------------------------------------
# Hearing Sheet <-> JSON (lưu lịch sử) và <-> XLSX (để trao đổi với Partner)
# ---------------------------------------------------------------------------

def save_hearing_sheet_json(sheet: HearingSheet, session_id: str, version: int) -> str:
    folder = os.path.join(SESSIONS_DIR, session_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"hearing_sheet_v{version}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sheet.model_dump(), f, ensure_ascii=False, indent=2)
    return path


HEADER_ROW = ["Câu hỏi", "Câu trả lời"]


def export_hearing_sheet_xlsx(sheet: HearingSheet, path: str) -> str:
    """Xuất Hearing Sheet ra file XLSX — MỖI phần tử trong sheet.tables thành
    1 sheet Excel riêng (giữ đúng sheet_name gốc). Nếu sheet đó có `notes`
    (VD: tiêu chí đánh giá ký hiệu), ghi 1 dòng ghi chú ngay TRÊN header để
    Partner nhìn thấy, và để round-trip lại đúng khi đọc file trả lời."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # bỏ sheet mặc định, tự tạo đúng số sheet theo tables

    used_titles: set[str] = set()
    for table in sheet.tables:
        title = _safe_sheet_title(table.sheet_name, used_titles)
        ws = wb.create_sheet(title)

        if table.notes.strip():
            ws.append([f"[Ghi chú/Tiêu chí]: {table.notes}"])
            ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=2)

        ws.append(HEADER_ROW)
        for row in table.rows:
            ws.append([row.question, row.answer])

    if not sheet.tables:
        wb.create_sheet("HearingSheet")  # đảm bảo luôn có ít nhất 1 sheet hợp lệ

    if sheet.notes.strip():
        notes_ws = wb.create_sheet("Notes")
        notes_ws["A1"] = sheet.notes

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return path


def send_to_partner(sheet: HearingSheet, partner: str, version: int) -> str:
    """'Gửi cho Partner' = xuất file XLSX vào data/outbox/<partner>/."""
    folder = os.path.join(OUTBOX_DIR, partner)
    filename = f"hearing_sheet_v{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    path = os.path.join(folder, filename)
    return export_hearing_sheet_xlsx(sheet, path)


def check_inbox(partner: str, after_ts: float = 0.0) -> str | None:
    """
    Quét data/inbox/<partner>/ tìm file mới nhất (xlsx/pdf), CHỈ tính file có
    thời gian sửa đổi SAU `after_ts` (thường là thời điểm vừa gửi khảo sát
    vòng này cho Partner) — để tránh đọc nhầm lại file trả lời của vòng
    trước còn sót trong thư mục khi tự động quét vòng mới. Trả về None nếu
    chưa có file hợp lệ. Trong demo, Partner tự upload/đặt file trả lời vào
    đúng thư mục này.
    """
    folder = os.path.join(INBOX_DIR, partner)
    os.makedirs(folder, exist_ok=True)
    files = glob.glob(os.path.join(folder, "*.xlsx")) + glob.glob(os.path.join(folder, "*.pdf"))
    files = [f for f in files if os.path.getmtime(f) > after_ts]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def read_answered_xlsx(path: str) -> HearingSheet:
    """
    Đọc file XLSX Partner đã trả lời — CÙNG cấu trúc đã xuất ở
    export_hearing_sheet_xlsx (mỗi sheet Excel = 1 bảng). Header ("Câu hỏi" /
    "Câu trả lời") được TÌM chứ không giả định luôn ở dòng 1, vì có thể có 1
    dòng ghi chú/tiêu chí đứng trước header — mọi dòng trước header được gộp
    lại thành `notes` của bảng đó, để không mất tiêu chí đánh giá khi đọc lại.
    """
    wb = openpyxl.load_workbook(path, data_only=True)

    tables: list[SheetTable] = []
    for ws in wb.worksheets:
        if ws.title == "Notes":
            continue

        rows_iter = list(ws.iter_rows(values_only=True))

        header_idx = next(
            (i for i, r in enumerate(rows_iter) if r and r[0] and str(r[0]).strip() == HEADER_ROW[0]),
            None,
        )

        if header_idx is None:
            # Không tìm thấy header chuẩn -> coi cả sheet là dữ liệu thô (tương
            # thích ngược), không có ghi chú riêng.
            table_notes = ""
            data_rows = rows_iter
        else:
            table_notes = "\n".join(
                str(r[0]).strip() for r in rows_iter[:header_idx] if r and r[0] not in (None, "")
            )
            data_rows = rows_iter[header_idx + 1:]

        rows = []
        for row in data_rows:
            if row and row[0]:
                question = str(row[0]).strip()
                answer = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
                rows.append(QARow(question=question, answer=answer))

        if rows or table_notes:
            tables.append(SheetTable(sheet_name=ws.title, notes=table_notes, rows=rows))

    notes = ""
    if "Notes" in wb.sheetnames:
        notes = str(wb["Notes"]["A1"].value or "")

    return HearingSheet(title=os.path.basename(path), tables=tables, notes=notes)


def inbox_path_for(partner: str) -> str:
    path = os.path.join(INBOX_DIR, partner)
    os.makedirs(path, exist_ok=True)
    return path