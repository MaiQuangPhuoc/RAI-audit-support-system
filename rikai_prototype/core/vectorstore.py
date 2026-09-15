"""
Stub interface cho Qdrant — CHƯA implement thật ở giai đoạn prototype này.

Mục đích: định nghĩa trước "hình dạng" API mà REPORT_AGENT sẽ gọi, để khi
tích hợp Qdrant thật sau này chỉ cần thay nội dung hàm bên trong, không
phải sửa code ở agents/report_agent.py.

Ở giai đoạn hiện tại, mọi hàm trả về rỗng / no-op và không được coi là
nguồn dữ liệu thật — REPORT_AGENT phải luôn chạy tốt kể cả khi module này
không trả kết quả gì (Qdrant là nguồn optional).
"""
from typing import Optional


class VectorStoreStub:
    """Placeholder cho kết nối Qdrant thật. Chưa kết nối gì ở bước này."""

    def __init__(self):
        self.is_configured = False  # sẽ True khi có QDRANT_URL hợp lệ + đã implement thật

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Tra cứu Standard/Policy liên quan tới `query`.
        Hiện tại luôn trả về [] vì chưa tích hợp Qdrant thật.
        Khi implement thật: trả list[{"text": str, "source": str, "score": float}]
        """
        return []

    def is_available(self) -> bool:
        return self.is_configured


def get_vectorstore() -> VectorStoreStub:
    return VectorStoreStub()
