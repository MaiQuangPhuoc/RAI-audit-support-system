"""
Schema dùng chung cho toàn bộ prototype RIKAI — viết bằng Pydantic BaseModel
để đưa thẳng vào `llm_client.invoke_with_retries(..., output_model=...)`
(structured output của core/llm.py): LLM sẽ trả về đúng object theo schema
này, không cần tự parse JSON thủ công.

Nguyên tắc cốt lõi: Hearing Sheet = danh sách bảng (`tables`), MỖI bảng ứng
đúng 1 sheet trong file Excel gốc, GIỮ NGUYÊN cấu trúc cột thật của file gốc
(`columns` động, không cố định 2 cột "câu hỏi/câu trả lời") — vì Auditor yêu
cầu không được biến đổi cấu trúc dữ liệu gốc, LLM chỉ được dùng để hiểu nội
dung, không dùng để tái tạo bảng khi chưa có yêu cầu thay đổi.
Các trường "loại" (issue_type, overall_status) dùng Literal để LLM chỉ được
chọn đúng 1 trong các giá trị hợp lệ, không tự bịa nhãn khác.
"""
from typing import Literal
from attr import dataclass
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

class SheetTable(BaseModel):
    """1 bảng, tương ứng đúng 1 sheet trong file Excel gốc. QUAN TRỌNG: giữ
    NGUYÊN cấu trúc cột của file gốc Auditor gửi — không được ép về 2 cột
    cố định "câu hỏi/câu trả lời". File gốc có bao nhiêu cột, tên gì, thì
    `columns` phải có đúng bấy nhiêu, đúng tên đó, đúng thứ tự đó."""
    sheet_name: str = Field(description="Tên sheet gốc (giữ đúng như trong file Excel input)")
    notes: str = Field(
        default="",
        description="Mô tả/hướng dẫn/tiêu chí đánh giá RIÊNG của sheet này (VD: giải thích ý nghĩa "
                    "ký hiệu 〇/△/✕/－ dùng để trả lời). PHẢI giữ lại nếu sheet gốc có đoạn text "
                    "này — đây là thông tin quan trọng để phân tích câu trả lời ở bước sau.",
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Tên các cột, GIỮ NGUYÊN VĂN như trong file gốc (không đổi tên, không dịch, "
                    "không gộp/tách cột, không tự đặt thành 'câu hỏi'/'câu trả lời' nếu tên gốc "
                    "khác). Đúng thứ tự xuất hiện trong file gốc.",
    )
    rows: list[dict[str, str]] = Field(
        default_factory=list,
        description="Mỗi phần tử là 1 dòng dữ liệu, dạng {tên_cột: giá_trị}, dùng ĐÚNG tên cột đã "
                    "khai báo trong `columns`. Cột nào chưa có giá trị (VD: cột Partner cần điền) "
                    "để chuỗi rỗng, không bỏ qua key.",
    )


class HearingSheet(BaseModel):
    """Hearing Sheet — kết quả của AGENT_Create_hearing_sheet, được Auditor review.
    Nếu file input có N sheet, PHẢI có đúng N phần tử trong `tables`, không gộp
    câu hỏi của các sheet khác nhau vào chung 1 bảng."""
    title: str = Field(description="Tiêu đề Hearing Sheet")
    tables: list[SheetTable] = Field(default_factory=list, description="Danh sách bảng, mỗi phần tử = 1 sheet gốc")
    notes: str = Field(
        default="",
        description="Mô tả/ghi chú CHUNG áp dụng cho TOÀN BỘ Hearing Sheet (không riêng sheet nào). "
                    "Ghi chú riêng của từng sheet phải để trong tables[i].notes, KHÔNG gộp vào đây.",
    )


# ---------------------------------------------------------------------------
# Bước 3: AGENT_ANALYSIS
# ---------------------------------------------------------------------------
# Đánh giá TỪNG DÒNG (không chỉ liệt kê vấn đề) — mọi dòng trong Hearing Sheet
# đều có 1 RowAssessment, kể cả dòng không có vấn đề gì (status = khong_co_van_de).
# 4 trạng thái khớp đúng 4 bộ đếm trên UI (🔴🟡🟢⚪ theo tài liệu Asno).

RowStatus = Literal["can_xu_ly", "khuyen_nghi_xac_nhan", "khong_co_van_de", "chua_tra_loi"]
OverallStatus = Literal["dat", "chua_dat"]

ROW_STATUS_LABELS: dict[str, str] = {
    "can_xu_ly": "🔴 Cần xử lý",
    "khuyen_nghi_xac_nhan": "🟡 Khuyến nghị xác nhận",
    "khong_co_van_de": "🟢 Không có vấn đề",
    "chua_tra_loi": "⚪ Chưa trả lời",
}


class RowAssessment(BaseModel):
    """Đánh giá của AGENT_ANALYSIS cho ĐÚNG 1 dòng dữ liệu trong Hearing Sheet.
    PHẢI có đủ 1 RowAssessment cho MỖI dòng trong sheet đang phân tích — không
    được bỏ sót dòng nào, kể cả dòng hoàn toàn ổn (status = khong_co_van_de)."""
    sheet_name: str = Field(description="Tên sheet chứa dòng này")
    row_index: int = Field(description="Vị trí dòng trong table.rows (0-based, đúng thứ tự xuất hiện trong sheet)")
    item_ref: str = Field(
        description="Mô tả ngắn để hiển thị (VD: dùng giá trị cột đầu tiên/mã mục của dòng đó)"
    )
    status: RowStatus = Field(
        description="'can_xu_ly' = câu trả lời sai/mâu thuẫn hoặc thiếu phần bắt buộc, cần Auditor xử lý "
                     "ngay; 'khuyen_nghi_xac_nhan' = mơ hồ/dùng ký hiệu không rõ tiêu chí/lạc chủ đề "
                     "(bat_thuong), CẦN Auditor xác nhận lại nhưng chưa chắc là lỗi; 'khong_co_van_de' = "
                     "đã trả lời đầy đủ, rõ ràng, không có gì bất thường; 'chua_tra_loi' = cột câu trả lời "
                     "đang hoàn toàn trống."
    )
    is_anomaly: bool = Field(
        default=False,
        description="True nếu nội dung dòng này LẠC CHỦ ĐỀ so với các dòng còn lại trong cùng sheet "
                    "(không liên quan tới ngữ cảnh chung) — xem hướng dẫn phát hiện bất thường trong prompt.",
    )
    current_state: str = Field(
        default="", description="Đánh giá hiện trạng — tóm tắt Partner đang ở tình trạng nào dựa trên câu trả lời"
    )
    predicted_risk: str = Field(
        default="", description="Rủi ro được dự đoán nếu hiện trạng này không được cải thiện — "
                                 "CHỈ nêu khi có cơ sở rõ ràng từ dữ liệu, không tự suy diễn xa"
    )
    suggestion: str = Field(
        default="", description="Đề xuất cải thiện — CHỈ điền khi có cơ sở rõ ràng từ dữ liệu (VD: "
                                 "tiêu chí đánh giá của sheet, hoặc câu trả lời tốt hơn ở dòng tương tự), "
                                 "không tự bịa. Để trống nếu status = khong_co_van_de."
    )


class AnalysisResult(BaseModel):
    """Kết quả của AGENT_ANALYSIS — Auditor review trước khi chuyển REPORT_AGENT."""
    overall_status: OverallStatus = Field(
        description="'dat' nếu không còn dòng nào ở trạng thái can_xu_ly hoặc chua_tra_loi, ngược lại 'chua_dat'"
    )
    assessments: list[RowAssessment] = Field(
        default_factory=list, description="Đánh giá cho MỌI dòng đã phân tích (không chỉ dòng có vấn đề)"
    )
    summary: str = Field(default="", description="Tóm tắt ngắn gọn kết quả phân tích cho Auditor")

    def counts_by_status(self) -> dict[str, int]:
        """Đếm số dòng theo từng trạng thái — dùng cho màn hình danh sách kết
        quả phân tích (🔴🟡🟢⚪ N mục)."""
        counts = {k: 0 for k in ROW_STATUS_LABELS}
        for a in self.assessments:
            counts[a.status] = counts.get(a.status, 0) + 1
        return counts


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



class ChunkInterpretation(BaseModel):
    """Diễn giải của LLM cho ĐÚNG 1 SheetChunk (table-level, không tách dòng).
    KHÔNG chứa sheet_name/row_offset — các trường định danh này do code gán
    sau khi nhận response, không để LLM tự sinh ra."""
    understanding: str = Field(
        description="Diễn giải ý nghĩa/mục đích của bảng hoặc phần bảng này: đang hỏi gì, vì sao hỏi, "
                    "áp dụng cho đối tượng/hạng mục nào — CHỈ dựa trên nội dung cột/dòng/ghi chú đã có, "
                    "không suy diễn thêm thông tin ngoài dữ liệu."
    )
    fields_for_partner: list[str] = Field(
        default_factory=list,
        description="Tên các cột (đúng như trong `columns` gốc) hiện đang trống hoặc cần Partner điền, "
                    "dựa trên việc quan sát giá trị rỗng trong các dòng của batch này."
    )
    unclear_points: str = Field(
        default="",
        description="Điểm mơ hồ/thiếu rõ ràng mà Agent thấy trong bảng này (VD: ký hiệu không có giải "
                    "thích, tiêu chí chưa nêu rõ) — CHỈ nêu khi có cơ sở rõ từ dữ liệu, để trống nếu "
                    "không có gì bất thường. Đây là phần Auditor cần xác nhận trước khi gửi Partner."
    )

@dataclass
class ChunkReview:
    """1 dòng hiển thị trên UI review — ghép data thô (đã có sẵn) với diễn giải LLM."""
    sheet_name: str
    row_offset: int
    part_label: str
    raw_text: str                        # = chunk.text, hiển thị nguyên trạng
    interpretation: ChunkInterpretation | None   # None nếu chunk này lỗi khi gọi LLM
    error: str = ""                      # lý do lỗi, nếu có


class HearingSheetSummary(BaseModel):
    """Tổng hợp cách hiểu TOÀN BỘ Hearing Sheet — do LLM sinh ra 1 LẦN DUY NHẤT,
    dựa trên diễn giải của TẤT CẢ chunk đã phân tích thành công (không phải dữ
    liệu thô gốc), không suy diễn thêm ngoài các diễn giải đã có."""
    overall_understanding: str = Field(
        description="Tóm tắt Agent hiểu khảo sát này về mục đích, phạm vi và các nhóm nội dung chính, "
                    "dựa trên diễn giải của từng bảng/chunk đã có — không thêm thông tin ngoài đó."
    )
    fields_for_partner_summary: list[str] = Field(
        default_factory=list,
        description="Gộp và loại trùng các trường/cột cần Partner điền, tổng hợp từ fields_for_partner "
                    "của tất cả chunk."
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Gộp các điểm chưa rõ ràng cần Auditor xác nhận trước khi gửi Partner, tổng hợp từ "
                    "unclear_points của tất cả chunk (bỏ qua chunk có unclear_points rỗng)."
    )