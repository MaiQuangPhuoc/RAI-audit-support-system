"""
AGENT_Create_hearing_sheet

- Tạo Hearing Sheet lần đầu từ content + file Auditor cung cấp (qua
  ingestion.restructure, dùng structured output).
- Tóm tắt cách hiểu để Auditor review.
- Soạn lại Hearing Sheet khi Auditor góp ý, hoặc khi AGENT_ANALYSIS báo
  "chưa đạt" (vòng lặp AUDITOR REVIEW ANALYSIS -> agent này).
"""
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

    
from core.llm import call_llm
from core.schemas import AnalysisResult, HearingSheet
from ingestion.restructure import restructure_to_hearing_sheet
from prompts.hearing_sheet_prompts import REVISE_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT


def create_hearing_sheet(raw_text: str, title: str) -> HearingSheet:
    return restructure_to_hearing_sheet(raw_text, title=title)


def _sheet_to_text(sheet: HearingSheet) -> str:
    lines = [f"# {sheet.title}"]
    if sheet.notes.strip():
        lines.append(f"Ghi chú: {sheet.notes}")
    for row in sheet.rows:
        lines.append(f"- Câu hỏi: {row.question}\n  Trả lời: {row.answer or '(chưa có)'}")
    return "\n".join(lines)


def summarize_understanding(sheet: HearingSheet) -> str:
    return call_llm(SUMMARY_SYSTEM_PROMPT, _sheet_to_text(sheet), temperature=0.2)


def revise_hearing_sheet(
    previous_sheet: HearingSheet,
    auditor_feedback: str,
    analysis_result: AnalysisResult | None = None,
) -> HearingSheet:
    prev_text = _sheet_to_text(previous_sheet)

    analysis_text = ""
    if analysis_result is not None:
        issue_lines = [
            f"- [{i.issue_type}] Câu hỏi: {i.question} — {i.description}"
            + (f" | Đề xuất: {i.suggestion}" if i.suggestion else "")
            for i in analysis_result.issues
        ]
        analysis_text = (
            f"\n\nKết quả phân tích (trạng thái: {analysis_result.overall_status}):\n"
            f"{analysis_result.summary}\n" + "\n".join(issue_lines)
        )

    user_prompt = (
        f"Hearing Sheet phiên bản trước:\n{prev_text}"
        f"{analysis_text}\n\n"
        f"Góp ý của Auditor:\n{auditor_feedback.strip()}"
    )

    from core.llm import call_llm_structured
    new_sheet: HearingSheet = call_llm_structured(
        REVISE_SYSTEM_PROMPT, user_prompt, schema=HearingSheet, temperature=0.1
    )
    if not new_sheet.title:
        new_sheet.title = previous_sheet.title
    return new_sheet
