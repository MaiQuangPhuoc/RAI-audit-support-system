"""
Bước Intake: nhận content + partner + file từ Auditor, chuẩn hoá thành
AuditorIntake, và bóc tách text thô từ từng file đính kèm (PDF/XLSX).
"""
import os
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)





"""
Bước Intake: nhận content + partner + file từ Auditor, chuẩn hoá thành
AuditorIntake, và bóc tách text thô từ từng file đính kèm (PDF/XLSX).
"""
import os

from core.schemas import AuditorIntake
from ingestion import pdf_extractor, xlsx_extractor

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xlsm"}


def build_intake(content: str, partner: str, file_paths: list[str]) -> AuditorIntake:
    return AuditorIntake(content=content, partner=partner.strip(), file_paths=file_paths)


def parse_tagged_partners(content: str, known_partner_names: list[str]) -> list[str]:
    """
    Chỉ Partner nào được @ tên TRỰC TIẾP trong nội dung mới nhận được khảo sát
    (VD: nội dung có "@VendorA" thì chỉ VendorA nhận, VendorB không nhận dù
    đang có mặt trong hệ thống). So khớp theo danh sách tên Partner đã biết
    (known_partner_names) thay vì regex tự do, để tránh nhận nhầm ký tự '@'
    ngẫu nhiên trong nội dung (VD: email) thành tên Partner.
    """
    return [name for name in known_partner_names if name and f"@{name}" in content]


def extract_files_text(file_paths: list[str]) -> tuple[str, list[str]]:
    """
    Bóc tách text thô từ toàn bộ file đính kèm, gộp lại thành 1 chuỗi.
    Trả về (text_gộp, danh_sách_cảnh_báo).
    """
    texts = []
    warnings = []

    for path in file_paths:
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".pdf":
                texts.append(f"--- File: {os.path.basename(path)} ---\n" + pdf_extractor.extract_text(path))
            elif ext in (".xlsx", ".xlsm"):
                texts.append(f"--- File: {os.path.basename(path)} ---\n" + xlsx_extractor.extract_text(path))
            else:
                warnings.append(f"File '{os.path.basename(path)}' định dạng '{ext}' chưa được hỗ trợ, bị bỏ qua.")
        except Exception as e:
            warnings.append(f"Lỗi khi đọc file '{os.path.basename(path)}': {e}")

    return "\n\n".join(texts), warnings