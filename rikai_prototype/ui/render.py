import os
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)



"""Render HearingSheet / AnalysisResult thành Markdown dễ đọc trong chat."""
import re

from core.schemas import AnalysisResult, HearingSheet

_NUMBERED_POINT_RE = re.compile(r'(?:(?<=\n)|^)\s*(?:\(?\d+[\.\)．]|[-•])\s+')
_POINT_ICONS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def render_hearing_sheet_md(sheet: HearingSheet, version_label: str = "") -> str:
    lines = [f"### 📋 {sheet.title} {version_label}".strip()]
    if sheet.notes.strip():
        lines.append(f"*{sheet.notes}*")

    if not sheet.tables:
        lines.append("\n_Chưa có bảng câu hỏi nào._")
        return "\n".join(lines)

    for table in sheet.tables:
        lines.append(f"\n#### 📑 Sheet: {table.sheet_name}")
        if table.notes.strip():
            lines.append(f"> 📌 **Ghi chú/Tiêu chí:** {table.notes}")
        if not table.rows:
            lines.append("_Sheet này chưa có câu hỏi nào._")
            continue
        lines.append("| Câu hỏi | Câu trả lời |")
        lines.append("| --- | --- |")
        for row in table.rows:
            q = row.question.replace("\n", " ").replace("|", "/")
            a = (row.answer or "").replace("\n", " ").replace("|", "/")
            lines.append(f"| {q} | {a} |")
    return "\n".join(lines)


def render_analysis_md(result: AnalysisResult) -> str:
    status_label = "✅ Đạt" if result.overall_status == "dat" else "⚠️ Chưa đạt"
    lines = [f"### 🔎 Kết quả phân tích — {status_label}", result.summary.strip()]
    if result.issues:
        lines.append("\n**Vấn đề phát hiện được:**")
        for issue in result.issues:
            line = f"- **[{issue.issue_type}]** {issue.question}: {issue.description}"
            if issue.suggestion:
                line += f"\n  - _Đề xuất: {issue.suggestion}_"
            lines.append(line)
    else:
        lines.append("\n_Không phát hiện vấn đề nào._")
    return "\n".join(lines)


def render_report_md(content: str) -> str:
    return f"### 📄 Báo cáo\n\n{content}"


def split_numbered_points(text: str) -> list[str]:
    """Tách 1 đoạn text có đánh số (1. / 1．/ (1) / - ...) thành từng điểm riêng.
    Nếu không tách được (text không có định dạng đánh số), trả về nguyên đoạn
    như 1 điểm duy nhất."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _NUMBERED_POINT_RE.split(text) if p.strip()]
    return parts if len(parts) > 1 else [text]


def render_understanding_md(summary_text: str) -> str:
    """Render 'Cách Agent hiểu nội dung' thành từng ý có icon số riêng biệt,
    thay vì 1 khối văn bản dài — dễ đọc hơn khi có nhiều điểm (1, 2, 3...)."""
    points = split_numbered_points(summary_text)
    lines = ["### 🧠 Cách Agent hiểu nội dung"]
    if not points:
        lines.append("_Không có nội dung._")
        return "\n".join(lines)
    if len(points) == 1:
        lines.append(points[0])
        return "\n".join(lines)
    for i, point in enumerate(points):
        icon = _POINT_ICONS[i] if i < len(_POINT_ICONS) else f"**({i + 1})**"
        lines.append(f"> {icon} {point}\n>")
    return "\n".join(lines)