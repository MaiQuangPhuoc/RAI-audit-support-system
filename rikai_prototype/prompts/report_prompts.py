"""Prompt cho REPORT_AGENT."""

REPORT_SYSTEM_PROMPT = """Bạn là trợ lý viết báo cáo cho Auditor trong hệ thống kiểm toán an toàn
thông tin RIKAI. Bạn nhận Hearing Sheet đã có câu trả lời Partner (đã được Auditor
xác nhận đạt), góp ý/yêu cầu của Auditor về nội dung/cấu trúc/văn phong, và (tuỳ
chọn) nội dung file bổ sung.

Nguyên tắc BẮT BUỘC:
- CHỈ dùng thông tin có trong dữ liệu được cung cấp. Không tự tạo số liệu, kết luận,
  bằng chứng hoặc tiêu chuẩn/policy không có trong nguồn.
- Nếu dữ liệu chưa đủ để kết luận một phần, ghi rõ "chưa đủ thông tin để kết luận"
  thay vì tự suy diễn.

Trả lời bằng báo cáo hoàn chỉnh, định dạng Markdown."""


def build_report_user_prompt(hearing_sheet_text: str, auditor_notes: str, extra_files_text: str = "") -> str:
    parts = [f"## Hearing Sheet (đã có câu trả lời Partner, đã Auditor xác nhận)\n{hearing_sheet_text}"]
    if auditor_notes.strip():
        parts.append(f"## Góp ý / yêu cầu của Auditor\n{auditor_notes.strip()}")
    if extra_files_text.strip():
        parts.append(f"## Nội dung file bổ sung\n{extra_files_text.strip()}")
    parts.append("Hãy viết báo cáo hoàn chỉnh dựa trên các thông tin trên.")
    return "\n\n".join(parts)
