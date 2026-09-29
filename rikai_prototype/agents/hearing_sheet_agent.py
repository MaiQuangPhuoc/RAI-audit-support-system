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
    
import asyncio

from core.llm import call_llm, call_llm_structured, acall_llm_structured
from core.schemas import AnalysisResult, ChunkInterpretation, ChunkReview, HearingSheet, HearingSheetSummary, SessionMemory
from core.chunking import DEFAULT_MAX_ROWS_PER_CHUNK, SheetChunk, split_into_sheet_chunks
from core.text_render import hearing_sheet_to_text
from ingestion import xlsx_extractor
from ingestion.intake import extract_files_text
from ingestion.restructure import restructure_to_hearing_sheet
from prompts.hearing_sheet_prompts import (
    REVISE_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    INTERPRETATION_SYSTEM_PROMPT,
    build_interpretation_user_prompt,
    HEARING_SHEET_SUMMARY_SYSTEM_PROMPT,
    build_hearing_sheet_summary_user_prompt,
)

_XLSX_EXTS = (".xlsx", ".xlsm")

# TODO: chuyển vào configs.py nếu project đã/sẽ có field tương ứng — tạm
# hardcode ở đây vì chưa được cung cấp nội dung configs.py để biết field nào
# đã có sẵn.
MAX_CONCURRENT_INTERPRET = 3


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


# ---------------------------------------------------------------------------
# Pipeline chunk-based: diễn giải song song từng chunk (core.chunking.SheetChunk)
# rồi tổng hợp 1 lần cuối cùng. KHÔNG sinh lại HearingSheet — chỉ sinh diễn
# giải đi kèm dữ liệu gốc để UI hiển thị song song (data thô + phân tích).
# ---------------------------------------------------------------------------

async def _interpret_chunk(
    chunk: SheetChunk,
    auditor_context: str,
    semaphore: asyncio.Semaphore,
) -> ChunkReview:
    async with semaphore:
        try:
            user_prompt = build_interpretation_user_prompt(chunk.text, auditor_context)
            result: ChunkInterpretation = await acall_llm_structured(
                INTERPRETATION_SYSTEM_PROMPT, user_prompt, schema=ChunkInterpretation,
                temperature=0.2, num_retries=3, retry_temperature_step=-0.1,
            )
            return ChunkReview(
                sheet_name=chunk.sheet_name,
                row_offset=chunk.row_offset,
                part_label=chunk.part_label,
                raw_text=chunk.text,
                interpretation=result,
            )
        except Exception as e:
            return ChunkReview(
                sheet_name=chunk.sheet_name,
                row_offset=chunk.row_offset,
                part_label=chunk.part_label,
                raw_text=chunk.text,
                interpretation=None,
                error=str(e),
            )


async def interpret_hearing_sheet(
    chunks: list[SheetChunk],
    auditor_context: str = "",
) -> list[ChunkReview]:
    """Phân tích song song từng chunk (tối đa MAX_CONCURRENT_INTERPRET request
    cùng lúc — xem giải thích cơ chế Semaphore ở nơi đã trao đổi). KHÔNG raise
    nếu 1 chunk lỗi — trả đủ list, chunk lỗi có interpretation=None kèm error,
    để UI cảnh báo rõ thay vì âm thầm thiếu dữ liệu."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_INTERPRET)
    tasks = [_interpret_chunk(c, auditor_context, semaphore) for c in chunks]
    return await asyncio.gather(*tasks)


async def build_hearing_sheet_review(
    chunks: list[SheetChunk],
    auditor_context: str = "",
) -> tuple[list[ChunkReview], HearingSheetSummary | None, str]:
    """Toàn bộ luồng 'hiểu Hearing Sheet' theo pipeline chunk-based:
    1) Phân tích song song từng chunk -> list[ChunkReview]
    2) Tổng hợp 1 LẦN DUY NHẤT (không song song), CHỈ từ các chunk phân tích
       THÀNH CÔNG -> HearingSheetSummary

    Trả về: (chunk_reviews đầy đủ cho UI hiển thị chi tiết + cảnh báo chunk lỗi,
    summary hoặc None nếu tổng hợp lỗi/không có chunk nào thành công, thông báo
    lỗi tổng hợp nếu có)."""
    chunk_reviews = await interpret_hearing_sheet(chunks, auditor_context)

    succeeded = [r for r in chunk_reviews if r.interpretation is not None]
    if not succeeded:
        return chunk_reviews, None, "Tất cả chunk đều lỗi khi phân tích — không đủ dữ liệu để tổng hợp."

    try:
        user_prompt = build_hearing_sheet_summary_user_prompt(succeeded, auditor_context)
        summary: HearingSheetSummary = await acall_llm_structured(
            HEARING_SHEET_SUMMARY_SYSTEM_PROMPT, user_prompt, schema=HearingSheetSummary,
            temperature=0.2, num_retries=2,
        )
        return chunk_reviews, summary, ""
    except Exception as e:
        return chunk_reviews, None, f"Lỗi khi tổng hợp: {e}"


async def create_and_review_hearing_sheet(
    file_paths: list[str],
    content: str,
    title: str,
    max_rows_per_chunk: int = DEFAULT_MAX_ROWS_PER_CHUNK,
) -> tuple[HearingSheet, list[str], list[ChunkReview], HearingSheetSummary | None, str]:
    """Hàm điều phối đầu-cuối, dùng cho UI gọi 1 lần duy nhất khi Auditor tạo
    Hearing Sheet lần đầu:
    1) create_hearing_sheet(...) -> HearingSheet (bóc tách thật, KHÔNG qua LLM
       nếu Auditor chỉ đính kèm XLSX — xem nguyên tắc ở đầu file)
    2) split_into_sheet_chunks(...) -> list[SheetChunk]
    3) build_hearing_sheet_review(chunks, auditor_context=content) -> phân tích
       song song từng chunk + tổng hợp 1 lần cuối

    `content` (mô tả/yêu cầu khảo sát Auditor gõ trực tiếp — AuditorIntake.content)
    được dùng làm auditor_context, truyền vào MỌI lời gọi diễn giải chunk lẫn bước
    tổng hợp, để LLM hiểu đúng bối cảnh Auditor đang muốn khảo sát gì.

    Trả về đủ mọi thứ UI cần hiển thị: HearingSheet gốc, warnings lúc bóc tách,
    chunk_reviews (data thô + diễn giải để hiển thị song song, kèm chunk lỗi nếu
    có), summary tổng hợp (hoặc None nếu lỗi), và thông báo lỗi tổng hợp nếu có."""
    sheet, warnings = create_hearing_sheet(file_paths, content, title)
    chunks = split_into_sheet_chunks(sheet, max_rows_per_chunk=max_rows_per_chunk)
    chunk_reviews, summary, summary_error = await build_hearing_sheet_review(chunks, auditor_context=content)
    return sheet, warnings, chunk_reviews, summary, summary_error