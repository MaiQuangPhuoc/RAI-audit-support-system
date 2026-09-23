"""
Schema dùng chung cho toàn bộ prototype RIKAI — viết bằng Pydantic BaseModel
để đưa thẳng vào `llm_client.invoke_with_retries(..., output_model=...)`
(structured output của core/llm.py): LLM sẽ trả về đúng object theo schema
này, không cần tự parse JSON thủ công.

Thiết kế đơn giản, đúng theo thống nhất với Auditor:
- Hearing Sheet = 1 danh sách câu hỏi/câu trả lời (đúng cấu trúc 2 cột như
  file Excel thật) + 1 trường "notes" cho mọi mô tả/ghi chú không thuộc
  dạng câu hỏi cụ thể.
- Các trường "loại" (issue_type, overall_status) dùng Literal để LLM chỉ
  được chọn đúng 1 trong các giá trị hợp lệ, không tự bịa nhãn khác.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Bước 1: INTAKE — input Auditor nhập
# ---------------------------------------------------------------------------

class AuditorIntake(BaseModel):
    """Input Auditor nhập ở bước đầu tiên (text + partner + file đính kèm)."""
    content: str = Field(description="Nội dung/yêu cầu khảo sát do Auditor mô tả")
    partner: str = Field(description="Tên Partner sẽ nhận khảo sát này")
    file_paths: list[str] = Field(default_factory=list, description="Đường dẫn file đính kèm (nếu có)")


# ---------------------------------------------------------------------------
# Bước 2: AGENT_Create_hearing_sheet
# ---------------------------------------------------------------------------

class QARow(BaseModel):
    """Một dòng câu hỏi/câu trả lời trong 1 bảng (1 sheet)."""
    question: str = Field(description="Câu hỏi / trường cần khảo sát")
    answer: str = Field(default="", description="Câu trả lời của Partner — để trống nếu chưa có")


class SheetTable(BaseModel):
    """1 bảng câu hỏi/câu trả lời, tương ứng đúng 1 sheet trong file Excel gốc
    (hoặc 1 nhóm câu hỏi cùng chủ đề nếu input là text/PDF không có khái niệm sheet)."""
    sheet_name: str = Field(description="Tên sheet gốc (giữ đúng như trong file Excel input)")
    notes: str = Field(
        default="",
        description="Mô tả/hướng dẫn/tiêu chí đánh giá RIÊNG của sheet này (VD: giải thích ý nghĩa "
                    "ký hiệu 〇/△/✕/－ dùng để trả lời). PHẢI giữ lại nếu sheet gốc có đoạn text "
                    "này — đây là thông tin quan trọng để phân tích câu trả lời ở bước sau.",
    )
    rows: list[QARow] = Field(default_factory=list, description="Danh sách câu hỏi/câu trả lời của sheet này")


class HearingSheet(BaseModel):
    """Hearing Sheet — kết quả của AGENT_Create_hearing_sheet, được Auditor review.
    Nếu file input có N sheet, PHẢI có đúng N phần tử trong `tables`, không gộp
    câu hỏi của các sheet khác nhau vào chung 1 bảng."""
    title: str = Field(description="Tiêu đề Hearing Sheet")
    tables: list[SheetTable] = Field(default_factory=list, description="Danh sách bảng, mỗi phần tử = 1 sheet gốc")
    notes: str | list[str] = "Mô tả/ghi chú CHUNG áp dụng cho TOÀN BỘ Hearing Sheet (không riêng sheet nào).Ghi chú riêng của từng sheet phải để trong tables[i].notes, KHÔNG gộp vào đây."
    # notes: str = Field(
    #     default="",
    #     description="Mô tả/ghi chú CHUNG áp dụng cho TOÀN BỘ Hearing Sheet (không riêng sheet nào). "
    #                 "Ghi chú riêng của từng sheet phải để trong tables[i].notes, KHÔNG gộp vào đây.",
    # )


# ---------------------------------------------------------------------------
# Bước 3: AGENT_ANALYSIS
# ---------------------------------------------------------------------------

IssueType = Literal["thieu", "sai_lech", "mo_ho"]
OverallStatus = Literal["dat", "chua_dat"]


class Issue(BaseModel):
    """Một vấn đề cụ thể AGENT_ANALYSIS phát hiện trên 1 câu hỏi."""
    question: str = Field(description="Câu hỏi liên quan tới vấn đề")
    issue_type: IssueType = Field(
        description="'thieu' = chưa trả lời/thiếu thông tin; "
                     "'sai_lech' = không khớp câu hỏi/mâu thuẫn; "
                     "'mo_ho' = trả lời chung chung, chưa đủ rõ"
    )
    description: str = Field(description="Mô tả vấn đề")
    suggestion: Optional[str] = Field(
        default=None, description="Đề xuất — CHỈ điền khi có cơ sở rõ ràng từ dữ liệu, không tự suy diễn"
    )


class AnalysisResult(BaseModel):
    """Kết quả của AGENT_ANALYSIS — Auditor review trước khi chuyển REPORT_AGENT."""
    overall_status: OverallStatus = Field(
        description="'dat' nếu toàn bộ câu trả lời đủ/đúng/rõ ràng, ngược lại 'chua_dat'"
    )
    issues: list[Issue] = Field(default_factory=list, description="Danh sách vấn đề phát hiện được")
    summary: str = Field(default="", description="Tóm tắt ngắn gọn kết quả phân tích cho Auditor")


# ---------------------------------------------------------------------------
# Memory — lịch sử các vòng góp ý/phân tích trong CÙNG 1 phiên làm việc, để
# agent (khi soạn lại Hearing Sheet hoặc phân tích lại) có đủ ngữ cảnh các
# vòng trước, không chỉ thấy vòng gần nhất. Đây là dữ liệu nội bộ (không phải
# structured output của LLM) nên không cần Literal ép kiểu chặt như trên.
# ---------------------------------------------------------------------------

MemoryStage = Literal["hearing_sheet_feedback", "analysis_result", "report_feedback"]


class MemoryEvent(BaseModel):
    """1 sự kiện được ghi vào bộ nhớ phiên làm việc."""
    stage: MemoryStage = Field(description="Giai đoạn phát sinh sự kiện")
    content: str = Field(description="Nội dung tóm tắt sự kiện (góp ý Auditor, hoặc tóm tắt phân tích)")


class SessionMemory(BaseModel):
    """Bộ nhớ của 1 phiên làm việc — tích luỹ theo thời gian, KHÔNG bị ghi đè
    khi tạo phiên bản Hearing Sheet mới, để agent luôn có đủ ngữ cảnh lịch sử."""
    session_id: str
    partner: str
    events: list[MemoryEvent] = Field(default_factory=list)

    def add(self, stage: MemoryStage, content: str) -> None:
        if content.strip():
            self.events.append(MemoryEvent(stage=stage, content=content.strip()))

    def as_text(self, max_events: int = 20) -> str:
        """Render lịch sử thành text để đưa vào prompt. Giới hạn số sự kiện gần
        nhất để tránh prompt phình to vô hạn qua nhiều vòng lặp."""
        if not self.events:
            return ""
        recent = self.events[-max_events:]
        lines = [f"[{e.stage}] {e.content}" for e in recent]
        return "\n".join(lines)