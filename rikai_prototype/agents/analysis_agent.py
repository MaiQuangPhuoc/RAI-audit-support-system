"""AGENT_ANALYSIS — kiểm tra câu trả lời Partner đúng/đủ/rõ, dùng structured output."""

import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.chunking import split_into_sheet_chunks
from core.llm import call_llm_structured
from core.schemas import AnalysisResult, HearingSheet, SessionMemory
from prompts.analysis_prompts import ANALYSIS_SYSTEM_PROMPT


def analyze_partner_answers(
    sheet: HearingSheet,
    memory: SessionMemory | None = None,
    on_sheet_start=None,
    on_sheet_done=None,
) -> AnalysisResult:
    """
    Phân tích từng sheet RIÊNG BIỆT (không gộp toàn bộ Hearing Sheet vào 1
    lần gọi LLM), rồi gộp kết quả lại thành 1 AnalysisResult duy nhất.

    on_sheet_start(sheet_name) / on_sheet_done(sheet_name, elapsed_seconds):
    callback tuỳ chọn để UI hiển thị tiến trình + thời gian xử lý từng sheet
    (VD: "Đang phân tích 基本情報... 12:23:12 → 12:23:18 (6s)"). Không truyền
    thì bỏ qua, không ảnh hưởng logic phân tích.
    """
    import time

    chunks = split_into_sheet_chunks(sheet)
    print(f"AGENT_ANALYSIS: Tách Hearing Sheet thành {len(chunks)} chunk (mỗi chunk = 1 sheet) để phân tích riêng biệt")
    if not chunks:
        return AnalysisResult(overall_status="dat", issues=[], summary="Hearing Sheet không có dữ liệu để phân tích.")

    memory_text = ""
    if memory is not None:
        history = memory.as_text()
        if history:
            memory_text = (
                "\n\nLỊCH SỬ các vòng phân tích/góp ý trước đó trong phiên này "
                "(tham khảo để biết vấn đề nào đã từng nêu ra, tránh lặp lại "
                "nguyên văn nếu Partner đã trả lời rõ ràng hơn ở vòng này):\n" + history
            )

    all_issues = []
    all_summaries = []
    overall_status = "dat"

    for chunk in chunks:
        print(f"AGENT_ANALYSIS: Đang phân tích sheet '{chunk.sheet_name}'")
        print(f"Chunk : {chunk.text}")
        if on_sheet_start:
            on_sheet_start(chunk.sheet_name)
        t0 = time.time()

        user_prompt = chunk.text + memory_text
        result = call_llm_structured(
            ANALYSIS_SYSTEM_PROMPT, user_prompt, schema=AnalysisResult, temperature=0.1
        )

        elapsed = time.time() - t0
        if on_sheet_done:
            on_sheet_done(chunk.sheet_name, elapsed)

        all_issues.extend(result.issues)
        if result.summary.strip():
            all_summaries.append(f"[{chunk.sheet_name}] {result.summary.strip()}")
        if result.overall_status == "chua_dat":
            overall_status = "chua_dat"

    return AnalysisResult(
        overall_status=overall_status,
        issues=all_issues,
        summary="\n".join(all_summaries),
    )