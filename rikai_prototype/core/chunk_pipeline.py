"""
Build Hearing Sheet chunks for LLM analysis.

Flow:
    XLSX file
        -> extract_structured()
        -> HearingSheet
        -> split_into_sheet_chunks()
        -> list[SheetChunk]

This module does NOT create embeddings and does NOT write to a vector store.d
The returned SheetChunk objects are intended to be reused by later LLM steps.
"""
import os
import sys

# from rikai_prototype.core.llm_of import call_llm
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from core.schemas import HearingSheet
from core.chunking import (
    SheetChunk,
    split_into_sheet_chunks,
)
from ingestion.xlsx_extractor import extract_structured


def build_hearing_sheet_chunks(
    file_path: str,
    title: str = "Hearing Sheet",
    notes: str = "",
    max_rows_per_chunk: int = 30,
) -> list[SheetChunk]:
    """
    Read an XLSX file, convert its extracted tables into a HearingSheet,
    then split it into LLM-ready chunks.

    Parameters
    ----------
    file_path:
        Path to the source XLSX file.
    title:
        Title assigned to the HearingSheet wrapper.
    notes:
        Notes that apply to the whole HearingSheet.
    max_rows_per_chunk:
        Maximum number of rows included in one chunk for a single table.

    Returns
    -------
    list[SheetChunk]
        Chunk objects that can be passed to a later LLM analysis step.
    """
    tables = extract_structured(file_path)

    hearing_sheet = HearingSheet(
        title=title,
        tables=tables,
        notes=notes,
    )

    return split_into_sheet_chunks(
        hearing_sheet,
        max_rows_per_chunk=max_rows_per_chunk,
    )


def print_hearing_sheet_chunks(chunks: list[SheetChunk]) -> None:
    """Print chunks to the terminal for manual inspection."""
    print(f"Total chunks: {len(chunks)}")

    for index, chunk in enumerate(chunks, start=1):
        print("\n" + "=" * 80)
        print(f"CHUNK {index}/{len(chunks)}")
        print(f"sheet_name : {chunk.sheet_name}")
        print(f"row_offset : {chunk.row_offset}")
        print(f"part       : {chunk.part_label or 'single part'}")
        print("-" * 80)
        print(chunk.text)


def build_and_print_hearing_sheet_chunks(
    file_path: str,
    title: str = "Hearing Sheet",
    notes: str = "",
    max_rows_per_chunk: int = 30,
) -> list[SheetChunk]:
    """
    Convenience function for prototype testing.

    Returns the same chunks that the later LLM pipeline can reuse,
    while also printing them to the terminal.
    """
    chunks = build_hearing_sheet_chunks(
        file_path=file_path,
        title=title,
        notes=notes,
        max_rows_per_chunk=max_rows_per_chunk,
    )

    print_hearing_sheet_chunks(chunks)
    return chunks


if __name__ == "__main__":
    chunks = build_and_print_hearing_sheet_chunks(
        r"D:\PHUOC\RAI_LLM\rikai_prototype2\rikai_prototype\data\input\xlsx_data_llm.xlsx"
    )

    # `chunks` is intentionally kept as SheetChunk objects.
    # A later LLM step can use, for example:
    #     chunk.text
    # without reparsing the XLSX file.