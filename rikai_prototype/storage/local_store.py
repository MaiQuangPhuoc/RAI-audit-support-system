"""
Lưu trữ local cho prototype:
- Lưu/đọc Hearing Sheet dạng JSON (lịch sử phiên làm việc).
- "Gửi cho Partner" = xuất Hearing Sheet ra file XLSX (GIỮ NGUYÊN cấu trúc cột
  của từng sheet đúng như file gốc Auditor — không ép về 2 cột cố định) vào
  thư mục data/outbox/<partner>/.
- "Nhận từ Partner" = quét thư mục data/inbox/<partner>/ xem có file mới không.
  Đây là cách mô phỏng đơn giản cho việc gửi/nhận qua lại với Partner (thực tế
  Partner trả lời thủ công ngoài hệ thống — không thuộc phạm vi xử lý AI).

Lưu ý: việc "tự động chạy khi có file mới" dùng st.fragment(run_every=60) ở
tầng UI (ui/chat_app.py) để tự quét mỗi 60 giây, thay cho việc Auditor phải
bấm nút thủ công.
"""
import glob
import json
import os
import shutil
import uuid
from datetime import datetime
import sys , os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import openpyxl

import configs
from core.schemas import HearingSheet, SheetTable

OUTBOX_DIR = os.path.join(configs.DATA_DIR, "outbox")
INBOX_DIR = os.path.join(configs.DATA_DIR, "inbox")
SESSIONS_DIR = configs.SESSIONS_DIR

os.makedirs(OUTBOX_DIR, exist_ok=True)
os.makedirs(INBOX_DIR, exist_ok=True)

# Ký tự Excel KHÔNG cho phép trong tên sheet, và giới hạn 31 ký tự.
_INVALID_SHEET_CHARS = set('[]:*?/\\')

# Đánh dấu dòng ghi chú/tiêu chí đứng trên header, để đọc lại phân biệt được
# với dòng header thật (vì tên cột giờ là ĐỘNG, không biết trước để so khớp).
_NOTES_PREFIX = "[Ghi chú/Tiêu chí]: "


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


def export_hearing_sheet_xlsx(sheet: HearingSheet, path: str) -> str:
    """Xuất Hearing Sheet ra file XLSX — MỖI phần tử trong sheet.tables thành
    1 sheet Excel riêng (giữ đúng sheet_name gốc), GIỮ NGUYÊN đúng số cột và
    tên cột (`table.columns`) như file gốc Auditor — KHÔNG ép về 2 cột cố định.
    Nếu sheet có `notes` (VD: tiêu chí đánh giá ký hiệu), ghi 1 dòng ghi chú
    ngay TRÊN header để Partner nhìn thấy, và để round-trip đúng khi đọc lại."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # bỏ sheet mặc định, tự tạo đúng số sheet theo tables

    used_titles: set[str] = set()
    for table in sheet.tables:
        title = _safe_sheet_title(table.sheet_name, used_titles)
        ws = wb.create_sheet(title)

        if table.notes.strip():
            ws.append([f"{_NOTES_PREFIX}{table.notes}"])
            span = max(len(table.columns), 1)
            ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=span)

        if table.columns:
            ws.append(table.columns)
            for row in table.rows:
                ws.append([row.get(c, "") for c in table.columns])

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


def send_original_file_to_partner(original_path: str, partner: str) -> str:
    """
    Gửi THẲNG bản sao y hệt (byte-for-byte, dùng shutil.copy2) file gốc Auditor
    đã upload cho Partner — dùng khi Auditor CHƯA yêu cầu thay đổi gì, để đảm
    bảo giống 100% file gốc (không đi qua bất kỳ bước tái tạo/export nào có
    thể làm lệch định dạng, style, hay dữ liệu).
    """
    folder = os.path.join(OUTBOX_DIR, partner)
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(original_path)[1] or ".xlsx"
    filename = f"hearing_sheet_v1_original_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    dest_path = os.path.join(folder, filename)
    shutil.copy2(original_path, dest_path)
    return dest_path


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
    Đọc file XLSX Partner đã trả lời. Dùng lại chính `xlsx_extractor.extract_structured()`
    (cùng logic tách text/bảng đã kiểm chứng) — nên đọc đúng cả 2 trường hợp:
    file do hệ thống tự xuất (có dòng ghi chú đánh dấu) VÀ file gốc gửi thẳng
    không qua chỉnh sửa (có thể có dòng mô tả tự do đứng trước bảng thật, kiểu
    file khảo sát thật của Auditor).
    """
    from ingestion.xlsx_extractor import extract_structured

    all_tables = extract_structured(path)

    top_level_notes = ""
    tables: list[SheetTable] = []
    for t in all_tables:
        if t.sheet_name == "Notes" and not t.columns and not t.rows:
            top_level_notes = t.notes
            continue
        if not t.columns and not t.rows and not t.notes.strip():
            continue  # sheet rỗng hoàn toàn, bỏ qua
        tables.append(t)

    return HearingSheet(title=os.path.basename(path), tables=tables, notes=top_level_notes)


def inbox_path_for(partner: str) -> str:
    path = os.path.join(INBOX_DIR, partner)
    os.makedirs(path, exist_ok=True)
    return path