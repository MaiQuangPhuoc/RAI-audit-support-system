"""
Tái cấu trúc text thô (đã bóc tách từ file + content Auditor nhập) thành
HearingSheet có cấu trúc, bằng cách gọi LLM với structured output
(schema = HearingSheet). Đây là bước quan trọng nhất: dữ liệu càng sạch,
LLM ở các bước sau càng ít hiểu sai.
"""
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    
from core.llm import call_llm_structured
from core.schemas import HearingSheet
from prompts.hearing_sheet_prompts import RESTRUCTURE_SYSTEM_PROMPT


def restructure_to_hearing_sheet(raw_text: str, title: str = "Hearing Sheet") -> HearingSheet:
    user_prompt = (
        f"Tiêu đề dự kiến: {title}\n\n"
        f"Nội dung thô cần tái cấu trúc:\n{raw_text.strip() or '(không có nội dung)'}"
    )
    result: HearingSheet = call_llm_structured(
        RESTRUCTURE_SYSTEM_PROMPT, user_prompt, schema=HearingSheet, temperature=0.1
    )
    if not result.title:
        result.title = title
    return result
