"""Bóc tách text thô từ file PDF — chỉ lấy chữ ra, không diễn giải ý nghĩa."""
import pdfplumber


def extract_text(file_path: str) -> str:
    """Đọc toàn bộ text trong file PDF, nối các trang lại thành 1 chuỗi."""
    pages_text = []
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(f"[Trang {page_num}]\n{text.strip()}")
    return "\n\n".join(pages_text)
