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
    """Một dòng câu hỏi/câu trả lời trong Hearing Sheet."""
    question: str = Field(description="Câu hỏi / trường cần khảo sát")
    answer: str = Field(default="", description="Câu trả lời của Partner — để trống nếu chưa có")


class HearingSheet(BaseModel):
    """Hearing Sheet — kết quả của AGENT_Create_hearing_sheet, được Auditor review."""
    title: str = Field(description="Tiêu đề Hearing Sheet")
    rows: list[QARow] = Field(default_factory=list, description="Danh sách câu hỏi/câu trả lời")
    notes: str = Field(default="", description="Mô tả/ghi chú/bối cảnh chung, không thuộc bảng câu hỏi")


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
