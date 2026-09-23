"""AGENT_ANALYSIS — kiểm tra câu trả lời Partner đúng/đủ/rõ, dùng structured output."""

import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)



from core.llm import call_llm_structured
from core.schemas import AnalysisResult, HearingSheet, SessionMemory
from prompts.analysis_prompts import ANALYSIS_SYSTEM_PROMPT


def _sheet_to_text(sheet: HearingSheet) -> str:
    lines = [f"# {sheet.title} (đã có câu trả lời Partner)"]
    if sheet.notes.strip():
        lines.append(f"Ghi chú: {sheet.notes}")
    for table in sheet.tables:
        lines.append(f"\n## Sheet: {table.sheet_name}")
        if table.notes.strip():
            lines.append(f"[Ghi chú/Tiêu chí đánh giá của sheet này — PHẢI dùng đúng tiêu chí này khi đánh giá]: {table.notes}")
        for row in table.rows:
            lines.append(f"- Câu hỏi: {row.question}\n  Trả lời: {row.answer or '(CHƯA TRẢ LỜI)'}")
    return "\n".join(lines)


def analyze_partner_answers(sheet: HearingSheet, memory: SessionMemory | None = None) -> AnalysisResult:
    user_prompt = _sheet_to_text(sheet)

    if memory is not None:
        history = memory.as_text()
        if history:
            user_prompt += (
                "\n\nLỊCH SỬ các vòng phân tích/góp ý trước đó trong phiên này "
                "(tham khảo để biết vấn đề nào đã từng nêu ra, tránh lặp lại "
                "nguyên văn nếu Partner đã trả lời rõ ràng hơn ở vòng này):\n" + history
            )

    return call_llm_structured(ANALYSIS_SYSTEM_PROMPT, user_prompt, schema=AnalysisResult, temperature=0.1)