"""
AGENT_Create_hearing_sheet

QUAN TRỌNG (nguyên tắc cốt lõi): nếu Auditor CHỈ đính kèm file XLSX (không có
PDF), Hearing Sheet được bóc tách TRỰC TIẾP bằng code
(ingestion.xlsx_extractor.extract_structured) — KHÔNG đi qua LLM để tái tạo
bảng. Điều này đảm bảo khi Auditor chưa yêu cầu thay đổi gì, dữ liệu gửi cho
Partner giữ ĐÚNG 100% cấu trúc cột và nội dung gốc — không có rủi ro LLM làm
lệch dữ liệu dù không ai yêu cầu sửa. LLM chỉ được dùng để TÓM TẮT/HIỂU nội
dung cho Auditor xem (summarize_understanding), và để SOẠN LẠI khi Auditor
thật sự đưa ra góp ý/yêu cầu thay đổi (revise_hearing_sheet) — đây là 2
trường hợp DUY NHẤT cần LLM ở agent này.

Nếu có file PDF (không thể bóc tách bảng đáng tin cậy bằng code thuần), hoặc
Auditor chỉ nhập text không kèm file, vẫn cần LLM để cấu trúc hoá — có cảnh
báo riêng cho Auditor biết trường hợp này có rủi ro sai lệch nhẹ.
"""
import os
import sys , os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
from core.llm import call_llm, call_llm_structured
from core.schemas import AnalysisResult, HearingSheet, SessionMemory
from core.text_render import hearing_sheet_to_text
from ingestion import xlsx_extractor
from ingestion.intake import extract_files_text
from ingestion.restructure import restructure_to_hearing_sheet
from prompts.hearing_sheet_prompts import REVISE_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT

_XLSX_EXTS = (".xlsx", ".xlsm")


def create_hearing_sheet(file_paths: list[str], content: str, title: str) -> tuple[HearingSheet, list[str]]:
    """Tạo Hearing Sheet lần đầu. Trả về (HearingSheet, warnings)."""
    xlsx_paths = [p for p in file_paths if p.lower().endswith(_XLSX_EXTS)]
    other_paths = [p for p in file_paths if not p.lower().endswith(_XLSX_EXTS)]

    if xlsx_paths and not other_paths:
        # Đường đi AN TOÀN NHẤT: bóc tách trực tiếp bằng code, không qua LLM.
        tables = []
        warnings: list[str] = []
        for path in xlsx_paths:
            try:
                tables.extend(xlsx_extractor.extract_structured(path))
            except Exception as e:
                warnings.append(f"Lỗi khi bóc tách file '{os.path.basename(path)}': {e}")
        sheet = HearingSheet(title=title, tables=tables, notes=content.strip())
        return sheet, warnings

    # Có PDF hoặc không có file XLSX nào -> bắt buộc qua LLM để cấu trúc hoá.
    files_text, warnings = extract_files_text(file_paths)
    raw_text = content + ("\n\n" + files_text if files_text else "")
    sheet = restructure_to_hearing_sheet(raw_text, title=title)
    if other_paths:
        warnings.append(
            "Có file PDF trong số file đính kèm nên phần này phải qua LLM để cấu trúc hoá "
            "(khác với XLSX, không bóc tách trực tiếp bằng code được) — có thể có sai lệch nhẹ "
            "so với file gốc, Auditor nên review kỹ trước khi gửi Partner."
        )
    return sheet, warnings


def summarize_understanding(sheet: HearingSheet) -> str:
    return call_llm(SUMMARY_SYSTEM_PROMPT, hearing_sheet_to_text(sheet), temperature=0.2)


def revise_hearing_sheet(
    previous_sheet: HearingSheet,
    auditor_feedback: str,
    analysis_result: AnalysisResult | None = None,
    memory: SessionMemory | None = None,
) -> HearingSheet:
    prev_text = hearing_sheet_to_text(previous_sheet)

    analysis_text = ""
    if analysis_result is not None:
        issue_lines = [
            f"- [{i.issue_type}] Sheet: {i.sheet_name} | Dòng: {i.item_ref} — {i.description}"
            + (f" | Đề xuất: {i.suggestion}" if i.suggestion else "")
            for i in analysis_result.issues
        ]
        analysis_text = (
            f"\n\nKết quả phân tích (trạng thái: {analysis_result.overall_status}):\n"
            f"{analysis_result.summary}\n" + "\n".join(issue_lines)
        )

    memory_text = ""
    if memory is not None:
        history = memory.as_text()
        if history:
            memory_text = (
                "\n\nLỊCH SỬ các vòng góp ý/phân tích trước đó trong phiên này "
                "(để không lặp lại vấn đề đã giải quyết, và giữ nhất quán với "
                "quyết định trước đó của Auditor):\n" + history
            )

    user_prompt = (
        f"Hearing Sheet phiên bản trước:\n{prev_text}"
        f"{analysis_text}"
        f"{memory_text}\n\n"
        f"Góp ý của Auditor (lần này):\n{auditor_feedback.strip()}"
    )

    new_sheet: HearingSheet = call_llm_structured(
        REVISE_SYSTEM_PROMPT, user_prompt, schema=HearingSheet, temperature=0.1
    )
    if not new_sheet.title:
        new_sheet.title = previous_sheet.title
    return new_sheet