"""Render HearingSheet / AnalysisResult thành Markdown dễ đọc trong chat."""
from core.schemas import AnalysisResult, HearingSheet


def render_hearing_sheet_md(sheet: HearingSheet, version_label: str = "") -> str:
    lines = [f"### 📋 {sheet.title} {version_label}".strip()]
    if sheet.notes.strip():
        lines.append(f"*{sheet.notes}*")
    lines.append("")
    if sheet.rows:
        lines.append("| Câu hỏi | Câu trả lời |")
        lines.append("| --- | --- |")
        for row in sheet.rows:
            q = row.question.replace("\n", " ").replace("|", "/")
            a = (row.answer or "").replace("\n", " ").replace("|", "/")
            lines.append(f"| {q} | {a} |")
    else:
        lines.append("_Chưa có câu hỏi nào._")
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
