"""REPORT_AGENT — viết báo cáo từ Hearing Sheet đã xác nhận + góp ý Auditor.
Chạy tốt kể cả không có Qdrant/file bổ sung (input tối thiểu: Hearing Sheet + góp ý)."""

import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

    
from core.llm import call_llm
from core.schemas import HearingSheet
from prompts.report_prompts import REPORT_SYSTEM_PROMPT, build_report_user_prompt


def _sheet_to_text(sheet: HearingSheet) -> str:
    lines = [f"# {sheet.title}"]
    if sheet.notes.strip():
        lines.append(f"Ghi chú: {sheet.notes}")
    for row in sheet.rows:
        lines.append(f"- {row.question}\n  Trả lời: {row.answer or '(chưa có)'}")
    return "\n".join(lines)


def generate_report(
    hearing_sheet: HearingSheet,
    auditor_notes: str,
    extra_files_text: str = "",
    previous_report: str | None = None,
    revision_feedback: str = "",
) -> str:
    notes = auditor_notes
    if previous_report and revision_feedback.strip():
        notes = (
            f"{auditor_notes}\n\n--- Đây là bản viết lại ---\n"
            f"Báo cáo trước (tóm tắt):\n{previous_report[:3000]}\n\n"
            f"Góp ý cần sửa từ Auditor:\n{revision_feedback.strip()}"
        )

    user_prompt = build_report_user_prompt(
        hearing_sheet_text=_sheet_to_text(hearing_sheet),
        auditor_notes=notes,
        extra_files_text=extra_files_text,
    )
    return call_llm(REPORT_SYSTEM_PROMPT, user_prompt, temperature=0.2, max_tokens=3000)
