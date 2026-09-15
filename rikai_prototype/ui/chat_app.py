"""Giao diện chat chính RIKAI — đơn giản, dạng ChatGPT/Claude."""
import streamlit as st

from agents.analysis_agent import analyze_partner_answers
from agents.hearing_sheet_agent import create_hearing_sheet, revise_hearing_sheet, summarize_understanding
from agents.report_agent import generate_report
from ingestion.intake import extract_files_text
from storage import local_store
from ui import session_state as ss
from ui.render import render_analysis_md, render_hearing_sheet_md, render_report_md

st.set_page_config(page_title="RIKAI — Trợ lý kiểm toán", page_icon="📋", layout="centered")


def _save_uploads(uploaded_files, subfolder: str) -> list[str]:
    return [local_store.save_uploaded_file(uf.getvalue(), uf.name, subfolder) for uf in (uploaded_files or [])]


def _replay_chat_log():
    for msg in st.session_state.chat_log:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


def run():
    ss.init_state()

    st.title("📋 RIKAI — Trợ lý khảo sát & viết báo cáo")
    st.caption("Auditor luôn là người review và xác nhận kết quả cuối cùng ở mỗi bước.")

    with st.sidebar:
        st.subheader("Phiên làm việc")
        if st.session_state.session_id:
            st.write(f"ID: `{st.session_state.session_id}`")
        if st.session_state.partner:
            st.write(f"Partner: `{st.session_state.partner}`")
        if st.button("🔄 Bắt đầu phiên mới"):
            ss.reset_all()
            st.rerun()

    _replay_chat_log()
    step = st.session_state.step

    # -----------------------------------------------------------------
    # BƯỚC 1: INTAKE — content + partner + file
    # -----------------------------------------------------------------
    if step == ss.STEP_INTAKE:
        with st.chat_message("assistant"):
            st.markdown(
                "Xin chào Auditor 👋 Nhập **nội dung khảo sát**, chọn **Partner nhận**, "
                "và đính kèm **file** nếu có (PDF/XLSX)."
            )

        partner = st.text_input("Tên Partner nhận khảo sát")
        uploaded_files = st.file_uploader(
            "File đính kèm (PDF/XLSX) — tuỳ chọn", type=["pdf", "xlsx", "xlsm"], accept_multiple_files=True
        )
        content = st.chat_input("Nhập nội dung khảo sát...")

        if content:
            if not partner.strip():
                st.warning("Vui lòng nhập tên Partner trước khi gửi nội dung.")
            else:
                session_id = st.session_state.session_id or local_store.new_session_id()
                st.session_state.session_id = session_id
                st.session_state.partner = partner.strip()

                ss.add_message("user", f"[Partner: {partner}]\n{content}")
                file_paths = _save_uploads(uploaded_files, f"{session_id}/uploads")

                with st.spinner("Đang bóc tách file và tạo Hearing Sheet..."):
                    files_text, warnings = extract_files_text(file_paths)
                    raw_text = content + ("\n\n" + files_text if files_text else "")
                    sheet = create_hearing_sheet(raw_text, title=f"Khảo sát {partner}")
                    st.session_state.hearing_sheet_history.append(sheet)
                    local_store.save_hearing_sheet_json(sheet, session_id, version=1)
                    understanding = summarize_understanding(sheet)

                reply = render_hearing_sheet_md(sheet, "(v1)")
                if warnings:
                    reply += "\n\n**Cảnh báo:**\n" + "\n".join(f"- {w}" for w in warnings)
                reply += f"\n\n---\n### 🧠 Cách Agent hiểu nội dung\n{understanding}"

                ss.add_message("assistant", reply)
                ss.set_step(ss.STEP_HEARING_SHEET_REVIEW)
                st.rerun()

    # -----------------------------------------------------------------
    # BƯỚC 2: AUDITOR REVIEW hearing sheet
    # -----------------------------------------------------------------
    elif step == ss.STEP_HEARING_SHEET_REVIEW:
        sheet = ss.current_hearing_sheet()
        approve = st.button("✅ OK — Gửi cho Partner", use_container_width=True)
        feedback = st.chat_input("Hoặc nhập góp ý để Agent sửa lại Hearing Sheet...")

        if approve:
            ss.add_message("user", "✅ OK — Gửi cho Partner")
            with st.spinner("Đang xuất file gửi Partner..."):
                out_path = local_store.send_to_partner(
                    sheet, st.session_state.partner, version=len(st.session_state.hearing_sheet_history)
                )
            ss.add_message(
                "assistant",
                f"Đã xuất Hearing Sheet ra file gửi Partner:\n\n`{out_path}`\n\n"
                f"(Demo: hãy copy 1 bản, điền cột **Câu trả lời**, rồi đặt vào thư mục "
                f"`{local_store.inbox_path_for(st.session_state.partner)}` để mô phỏng Partner gửi lại.)",
            )
            ss.set_step(ss.STEP_WAIT_PARTNER)
            st.rerun()
        elif feedback:
            ss.add_message("user", feedback)
            with st.spinner("Đang soạn lại Hearing Sheet theo góp ý..."):
                new_sheet = revise_hearing_sheet(sheet, auditor_feedback=feedback)
                st.session_state.hearing_sheet_history.append(new_sheet)
                local_store.save_hearing_sheet_json(
                    new_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                )
            ss.add_message(
                "assistant",
                render_hearing_sheet_md(new_sheet, f"(v{len(st.session_state.hearing_sheet_history)})"),
            )
            st.rerun()

    # -----------------------------------------------------------------
    # BƯỚC 3: chờ Partner — quét thư mục inbox
    # -----------------------------------------------------------------
    elif step == ss.STEP_WAIT_PARTNER:
        partner = st.session_state.partner
        st.info(f"Đang chờ Partner **{partner}** trả lời. Thư mục nhận: `{local_store.inbox_path_for(partner)}`")
        check = st.button("🔄 Kiểm tra file mới từ Partner")

        if check:
            found_path = local_store.check_inbox(partner)
            if not found_path:
                st.warning("Chưa có file nào trong thư mục nhận của Partner.")
            else:
                ss.add_message("user", f"📥 Đã tìm thấy file trả lời từ Partner: `{found_path}`")
                with st.spinner("Đang đọc câu trả lời và phân tích..."):
                    answered_sheet = local_store.read_answered_xlsx(found_path)
                    answered_sheet.title = ss.current_hearing_sheet().title
                    st.session_state.hearing_sheet_history.append(answered_sheet)
                    local_store.save_hearing_sheet_json(
                        answered_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                    )
                    analysis = analyze_partner_answers(answered_sheet)
                    st.session_state.analysis_history.append(analysis)

                reply = render_hearing_sheet_md(answered_sheet, "(đã có câu trả lời)")
                reply += "\n\n---\n" + render_analysis_md(analysis)
                ss.add_message("assistant", reply)
                ss.set_step(ss.STEP_ANALYSIS_REVIEW)
                st.rerun()

    # -----------------------------------------------------------------
    # BƯỚC 4: AUDITOR REVIEW ANALYSIS
    # -----------------------------------------------------------------
    elif step == ss.STEP_ANALYSIS_REVIEW:
        approve = st.button("✅ Đạt — Chuyển viết báo cáo", use_container_width=True)
        feedback = st.chat_input("Hoặc nhập vấn đề cần làm rõ để soạn lại Hearing Sheet gửi Partner...")

        if approve:
            ss.add_message("user", "✅ Đạt — Chuyển viết báo cáo")
            ss.add_message("assistant", "Đã xác nhận kết quả phân tích. Nhập góp ý/yêu cầu để tôi viết báo cáo.")
            ss.set_step(ss.STEP_REPORT_INPUT)
            st.rerun()
        elif feedback:
            ss.add_message("user", feedback)
            sheet = ss.current_hearing_sheet()
            analysis = ss.current_analysis()
            with st.spinner("Đang soạn lại Hearing Sheet để gửi lại Partner..."):
                new_sheet = revise_hearing_sheet(sheet, auditor_feedback=feedback, analysis_result=analysis)
                st.session_state.hearing_sheet_history.append(new_sheet)
                local_store.save_hearing_sheet_json(
                    new_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                )
                out_path = local_store.send_to_partner(
                    new_sheet, st.session_state.partner, len(st.session_state.hearing_sheet_history)
                )
            ss.add_message(
                "assistant",
                render_hearing_sheet_md(new_sheet, "(đã soạn lại)") + f"\n\nĐã gửi lại Partner: `{out_path}`",
            )
            ss.set_step(ss.STEP_WAIT_PARTNER)
            st.rerun()

    # -----------------------------------------------------------------
    # BƯỚC 5: nhập góp ý cho REPORT_AGENT
    # -----------------------------------------------------------------
    elif step == ss.STEP_REPORT_INPUT:
        extra_files = st.file_uploader(
            "File dữ kiện bổ sung (tuỳ chọn)", type=["pdf", "xlsx", "xlsm"], accept_multiple_files=True
        )
        auditor_notes = st.chat_input("Nhập yêu cầu/góp ý về nội dung, cấu trúc, văn phong báo cáo...")

        if auditor_notes:
            ss.add_message("user", auditor_notes)
            extra_text = ""
            if extra_files:
                paths = _save_uploads(extra_files, f"{st.session_state.session_id}/report_files")
                extra_text, _ = extract_files_text(paths)

            with st.spinner("Đang viết báo cáo..."):
                report = generate_report(ss.current_hearing_sheet(), auditor_notes, extra_files_text=extra_text)
                st.session_state.report_history.append(report)

            ss.add_message("assistant", render_report_md(report))
            ss.set_step(ss.STEP_REPORT_REVIEW)
            st.rerun()

    # -----------------------------------------------------------------
    # BƯỚC 6: FEEDBACK báo cáo
    # -----------------------------------------------------------------
    elif step == ss.STEP_REPORT_REVIEW:
        approve = st.button("✅ OK — Hoàn tất báo cáo", use_container_width=True)
        feedback = st.chat_input("Hoặc nhập góp ý để viết lại báo cáo...")

        if approve:
            ss.add_message("user", "✅ OK — Hoàn tất báo cáo")
            ss.add_message("assistant", "🎉 Báo cáo đã hoàn tất. Cảm ơn Auditor đã sử dụng RIKAI.")
            ss.set_step(ss.STEP_DONE)
            st.rerun()
        elif feedback:
            ss.add_message("user", feedback)
            with st.spinner("Đang viết lại báo cáo..."):
                report = generate_report(
                    ss.current_hearing_sheet(), auditor_notes="",
                    previous_report=ss.current_report(), revision_feedback=feedback,
                )
                st.session_state.report_history.append(report)
            ss.add_message("assistant", render_report_md(report))
            st.rerun()

    # -----------------------------------------------------------------
    elif step == ss.STEP_DONE:
        st.success("Phiên làm việc đã hoàn tất.")
        report = ss.current_report()
        if report:
            st.download_button("⬇️ Tải báo cáo (Markdown)", data=report, file_name="rikai_report.md", mime="text/markdown")
