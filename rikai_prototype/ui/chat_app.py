"""
Giao diện chat chính RIKAI.

Cấu trúc UI: 3 tab mô phỏng 3 người dùng khác nhau trong CÙNG 1 trình duyệt
(demo — thực tế mỗi người sẽ có phiên đăng nhập riêng):
- Tab "Auditor": toàn bộ luồng nghiệp vụ chính (intake -> hearing sheet ->
  phân tích -> báo cáo). Bên trong tab này chia 2 cột: trái là panel tài liệu
  gốc Auditor đính kèm (mặc định mở), phải là khung chat chính.
- Tab "Partner A" / "Partner B": mô phỏng góc nhìn của Partner — họ thấy
  file khảo sát Auditor gửi (qua thư mục outbox), và có thể upload file trả
  lời (ghi thẳng vào thư mục inbox) thay vì phải copy file thủ công.

GIỚI HẠN: Streamlit không hỗ trợ kéo-thả đổi độ rộng cột bằng chuột — tỷ lệ
cột ở đây cố định. Muốn kéo-thả thật cần viết custom component (React),
ngoài phạm vi prototype này.
"""
import glob
import os
from datetime import datetime
import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

    
import pandas as pd
import streamlit as st

from agents.analysis_agent import analyze_partner_answers
from agents.hearing_sheet_agent import create_hearing_sheet, revise_hearing_sheet, summarize_understanding
from agents.report_agent import generate_report
from core.schemas import HearingSheet, QARow, SheetTable
from ingestion.intake import extract_files_text, parse_tagged_partners
from storage import local_store
from ui import session_state as ss
from ui.render import render_analysis_md, render_hearing_sheet_md, render_report_md, render_understanding_md

st.set_page_config(page_title="RIKAI - Tro ly kiem toan", page_icon="📋", layout="wide")


def _save_uploads(uploaded_files, subfolder: str) -> list[str]:
    return [local_store.save_uploaded_file(uf.getvalue(), uf.name, subfolder) for uf in (uploaded_files or [])]


def _replay_chat_log():
    for msg in st.session_state.chat_log:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


def _render_editable_tables(sheet: HearingSheet, key_prefix: str) -> HearingSheet:
    """Hiển thị từng bảng (mỗi sheet) dưới dạng st.data_editor cho phép Auditor
    thêm/sửa/xoá dòng trực tiếp. Trả về HearingSheet theo đúng dữ liệu đang
    hiển thị trên các editor (đã phản ánh chỉnh sửa live nhờ Streamlit lưu
    state theo key), để nơi gọi tự quyết định lưu hay không."""
    edited_tables = []
    for ti, table in enumerate(sheet.tables):
        st.markdown(f"**Sheet: {table.sheet_name}**")
        if table.notes.strip():
            st.caption(f"Ghi chú/Tiêu chí: {table.notes}")

        rows_data = [{"Câu hỏi": r.question, "Câu trả lời": r.answer} for r in table.rows]
        df = pd.DataFrame(rows_data, columns=["Câu hỏi", "Câu trả lời"])

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"{key_prefix}_editor_{ti}",
            column_config={
                "Câu hỏi": st.column_config.TextColumn("Câu hỏi", width="medium"),
                "Câu trả lời": st.column_config.TextColumn("Câu trả lời", width="medium"),
            },
        )
        new_rows = [
            QARow(
                question=str(r["Câu hỏi"]).strip(),
                answer=str(r["Câu trả lời"]).strip() if pd.notna(r["Câu trả lời"]) else "",
            )
            for _, r in edited_df.iterrows()
            if str(r["Câu hỏi"]).strip()
        ]
        edited_tables.append(SheetTable(sheet_name=table.sheet_name, notes=table.notes, rows=new_rows))

    return HearingSheet(title=sheet.title, tables=edited_tables, notes=sheet.notes)


def _render_original_docs_panel():
    st.markdown("#### Tài liệu gốc")
    docs = st.session_state.uploaded_docs
    if not docs:
        st.caption("Chưa có tài liệu nào được đính kèm.")
        return
    for doc in docs:
        path = doc["path"]
        if not os.path.exists(path):
            continue
        with st.expander(f"{doc['name']}", expanded=False):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                st.download_button("Tải xuống", data=data, file_name=doc["name"], key=f"dl_doc_{doc['name']}_{path}")
            except Exception as e:
                st.caption(f"Không đọc được file: {e}")


def _render_partner_tab(key: str):
    default_name = st.session_state.partner_names.get(key, f"Partner_{key}")
    name = st.text_input(
        "Tên Partner này (Auditor phải gõ đúng @tên để gửi khảo sát tới đây)",
        value=default_name, key=f"partner_name_input_{key}",
    )
    name = name.strip() or default_name
    st.session_state.partner_names[key] = name

    st.divider()

    received = sorted(glob.glob(os.path.join(local_store.OUTBOX_DIR, name, "*.xlsx")), key=os.path.getmtime)
    sent = sorted(glob.glob(os.path.join(local_store.INBOX_DIR, name, "*.xlsx")), key=os.path.getmtime)
    events = [("received", p) for p in received] + [("sent", p) for p in sent]
    events.sort(key=lambda e: os.path.getmtime(e[1]))

    if not events:
        st.info(f"Chưa có khảo sát nào gửi tới {name}. Khi Auditor @{name} trong nội dung và gửi, file sẽ xuất hiện ở đây.")
    else:
        for kind, path in events:
            ts = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%H:%M:%S %d/%m")
            if kind == "received":
                with st.chat_message("assistant"):
                    st.markdown(f"Nhận khảo sát lúc {ts}\n\n`{os.path.basename(path)}`")
                    with open(path, "rb") as f:
                        st.download_button(
                            "Tải file khảo sát", data=f.read(), file_name=os.path.basename(path),
                            key=f"dl_recv_{key}_{path}",
                        )
            else:
                with st.chat_message("user"):
                    st.markdown(f"Đã gửi trả lời lúc {ts}\n\n`{os.path.basename(path)}`")

    st.divider()
    st.markdown("**Trả lời khảo sát**")
    uploaded = st.file_uploader(
        "Chọn file đã điền câu trả lời (giữ đúng cấu trúc file nhận được)",
        type=["xlsx", "xlsm"], key=f"partner_upload_{key}",
    )
    if uploaded is not None and st.button("Gửi trả lời cho Auditor", key=f"partner_send_{key}"):
        dest_dir = local_store.inbox_path_for(name)
        dest_path = os.path.join(dest_dir, uploaded.name)
        with open(dest_path, "wb") as f:
            f.write(uploaded.getvalue())
        st.success(f"Đã gửi trả lời: {uploaded.name}")
        st.rerun()


def _process_partner_reply(partner: str, found_path: str):
    ss.add_message("user", f"Đã tìm thấy file trả lời từ {partner}: `{found_path}`")
    memory = ss.ensure_memory(st.session_state.session_id, partner)
    with st.spinner("Đang đọc câu trả lời và phân tích..."):
        answered_sheet = local_store.read_answered_xlsx(found_path)
        answered_sheet.title = ss.current_hearing_sheet().title
        st.session_state.hearing_sheet_history.append(answered_sheet)
        local_store.save_hearing_sheet_json(
            answered_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
        )
        analysis = analyze_partner_answers(answered_sheet, memory=memory)
        memory.add("analysis_result", f"[{analysis.overall_status}] {analysis.summary}")
        st.session_state.analysis_history.append(analysis)

    reply = f"*(Partner trả lời: {partner})*\n\n" + render_hearing_sheet_md(answered_sheet, "(đã có câu trả lời)")
    reply += "\n\n---\n" + render_analysis_md(analysis)
    ss.add_message("assistant", reply)
    ss.set_step(ss.STEP_ANALYSIS_REVIEW)


@st.fragment(run_every=60)
def _auto_check_partner_fragment():
    """Tự động quét inbox của các Partner đang chờ mỗi 60 giây thay cho việc
    Auditor phải bấm nút. Nếu tìm thấy file mới, xử lý và rerun toàn app."""
    for partner in st.session_state.tagged_partners:
        after_ts = st.session_state.partner_sent_at.get(partner, 0.0)
        found_path = local_store.check_inbox(partner, after_ts=after_ts)
        if found_path:
            _process_partner_reply(partner, found_path)
            st.rerun()
            return
    st.caption(f"Tự động kiểm tra mỗi 60 giây - lần kiểm tra gần nhất: {datetime.now().strftime('%H:%M:%S')}")
    if st.button("Kiểm tra ngay"):
        st.rerun()


def _render_auditor_tab():
    col_docs, col_main = st.columns([1, 3])

    with col_docs:
        _render_original_docs_panel()

    with col_main:
        _replay_chat_log()
        step = st.session_state.step

        if step == ss.STEP_INTAKE:
            names = st.session_state.partner_names
            with st.chat_message("assistant"):
                st.markdown(
                    f"Xin chào Auditor. Nhập nội dung khảo sát, đính kèm file nếu có "
                    f"(PDF/XLSX), và @tên Partner ngay trong nội dung để chọn ai nhận "
                    f"(VD: @{names.get('a', 'VendorA')}). Chỉ Partner được @ mới nhận khảo sát này."
                )

            uploaded_files = st.file_uploader(
                "File đính kèm (PDF/XLSX) - tuỳ chọn", type=["pdf", "xlsx", "xlsm"], accept_multiple_files=True
            )
            content = st.chat_input(f"VD: Khảo sát bảo mật hệ thống @{names.get('a', 'VendorA')} ...")

            if content:
                known_names = [n for n in names.values() if n]
                tagged = parse_tagged_partners(content, known_names)
                if not tagged:
                    st.warning(
                        f"Không tìm thấy Partner nào được @ trong nội dung. "
                        f"Thêm VD: @{names.get('a', 'VendorA')} rồi gửi lại."
                    )
                else:
                    session_id = st.session_state.session_id or local_store.new_session_id()
                    st.session_state.session_id = session_id
                    st.session_state.tagged_partners = tagged
                    st.session_state.partner = tagged[0]
                    ss.ensure_memory(session_id, tagged[0])

                    ss.add_message("user", f"[@{', @'.join(tagged)}]\n{content}")
                    file_paths = _save_uploads(uploaded_files, f"{session_id}/uploads")
                    for uf, path in zip(uploaded_files or [], file_paths):
                        st.session_state.uploaded_docs.append({"name": uf.name, "path": path})

                    with st.spinner("Đang bóc tách file và tạo Hearing Sheet..."):
                        files_text, warnings = extract_files_text(file_paths)
                        raw_text = content + ("\n\n" + files_text if files_text else "")
                        sheet = create_hearing_sheet(raw_text, title=f"Khảo sát {', '.join(tagged)}")
                        st.session_state.hearing_sheet_history.append(sheet)
                        local_store.save_hearing_sheet_json(sheet, session_id, version=1)
                        understanding = summarize_understanding(sheet)

                    reply = render_hearing_sheet_md(sheet, "(v1)")
                    if warnings:
                        reply += "\n\n**Cảnh báo:**\n" + "\n".join(f"- {w}" for w in warnings)
                    reply += "\n\n---\n" + render_understanding_md(understanding)

                    ss.add_message("assistant", reply)
                    ss.set_step(ss.STEP_HEARING_SHEET_REVIEW)
                    st.rerun()

        elif step == ss.STEP_HEARING_SHEET_REVIEW:
            sheet = ss.current_hearing_sheet()

            with st.expander("Chỉnh sửa bảng trực tiếp (thêm/sửa/xoá dòng)", expanded=False):
                edited_sheet = _render_editable_tables(sheet, key_prefix="hs_review")
                if st.button("Lưu chỉnh sửa bảng"):
                    edited_sheet.title = sheet.title
                    st.session_state.hearing_sheet_history.append(edited_sheet)
                    local_store.save_hearing_sheet_json(
                        edited_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                    )
                    memory = ss.ensure_memory(st.session_state.session_id, st.session_state.partner)
                    memory.add("hearing_sheet_feedback", "Auditor tự chỉnh sửa bảng thủ công trên UI")
                    ss.add_message(
                        "assistant",
                        render_hearing_sheet_md(
                            edited_sheet, f"(v{len(st.session_state.hearing_sheet_history)} - sửa thủ công)"
                        ),
                    )
                    st.rerun()

            approve = st.button("OK - Gửi cho Partner", use_container_width=True)
            feedback = st.chat_input("Hoặc nhập góp ý để Agent sửa lại Hearing Sheet...")

            if approve:
                sheet = ss.current_hearing_sheet()
                ss.add_message("user", "OK - Gửi cho Partner")
                out_paths = []
                with st.spinner("Đang xuất file gửi Partner..."):
                    for partner in st.session_state.tagged_partners:
                        out_path = local_store.send_to_partner(
                            sheet, partner, version=len(st.session_state.hearing_sheet_history)
                        )
                        st.session_state.partner_sent_at[partner] = os.path.getmtime(out_path)
                        out_paths.append((partner, out_path))

                lines = ["Đã xuất Hearing Sheet gửi tới:"]
                for partner, path in out_paths:
                    lines.append(f"- {partner}: `{path}`")
                lines.append(
                    "\nSang tab của từng Partner để tải file, điền câu trả lời, rồi upload lại "
                    "ngay trong tab đó - hoặc hệ thống sẽ tự kiểm tra mỗi 60 giây."
                )
                ss.add_message("assistant", "\n".join(lines))
                ss.set_step(ss.STEP_WAIT_PARTNER)
                st.rerun()

            elif feedback:
                ss.add_message("user", feedback)
                memory = ss.ensure_memory(st.session_state.session_id, st.session_state.partner)
                with st.spinner("Đang soạn lại Hearing Sheet theo góp ý..."):
                    new_sheet = revise_hearing_sheet(sheet, auditor_feedback=feedback, memory=memory)
                    memory.add("hearing_sheet_feedback", feedback)
                    st.session_state.hearing_sheet_history.append(new_sheet)
                    local_store.save_hearing_sheet_json(
                        new_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                    )
                ss.add_message(
                    "assistant",
                    render_hearing_sheet_md(new_sheet, f"(v{len(st.session_state.hearing_sheet_history)})"),
                )
                st.rerun()

        elif step == ss.STEP_WAIT_PARTNER:
            partners_str = ", ".join(st.session_state.tagged_partners)
            st.info(f"Đang chờ trả lời từ: {partners_str}")
            _auto_check_partner_fragment()

        elif step == ss.STEP_ANALYSIS_REVIEW:
            sheet = ss.current_hearing_sheet()
            with st.expander("Chỉnh sửa câu trả lời trực tiếp trước khi phân tích lại", expanded=False):
                edited_sheet = _render_editable_tables(sheet, key_prefix="analysis_review")
                if st.button("Lưu chỉnh sửa & phân tích lại"):
                    edited_sheet.title = sheet.title
                    st.session_state.hearing_sheet_history.append(edited_sheet)
                    memory = ss.ensure_memory(st.session_state.session_id, st.session_state.partner)
                    with st.spinner("Đang phân tích lại..."):
                        analysis = analyze_partner_answers(edited_sheet, memory=memory)
                        memory.add(
                            "analysis_result",
                            f"[{analysis.overall_status}] {analysis.summary} (sau khi Auditor tự sửa)",
                        )
                        st.session_state.analysis_history.append(analysis)
                    reply = render_hearing_sheet_md(edited_sheet, "(đã sửa thủ công)") + "\n\n---\n" + render_analysis_md(analysis)
                    ss.add_message("assistant", reply)
                    st.rerun()

            approve = st.button("Đạt - Chuyển viết báo cáo", use_container_width=True)
            feedback = st.chat_input("Hoặc nhập vấn đề cần làm rõ để soạn lại Hearing Sheet gửi Partner...")

            if approve:
                ss.add_message("user", "Đạt - Chuyển viết báo cáo")
                ss.add_message("assistant", "Đã xác nhận kết quả phân tích. Nhập góp ý/yêu cầu để tôi viết báo cáo.")
                ss.set_step(ss.STEP_REPORT_INPUT)
                st.rerun()
            elif feedback:
                ss.add_message("user", feedback)
                sheet = ss.current_hearing_sheet()
                analysis = ss.current_analysis()
                memory = ss.ensure_memory(st.session_state.session_id, st.session_state.partner)
                with st.spinner("Đang soạn lại Hearing Sheet để gửi lại Partner..."):
                    new_sheet = revise_hearing_sheet(
                        sheet, auditor_feedback=feedback, analysis_result=analysis, memory=memory
                    )
                    memory.add("hearing_sheet_feedback", feedback)
                    st.session_state.hearing_sheet_history.append(new_sheet)
                    local_store.save_hearing_sheet_json(
                        new_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                    )
                    out_paths = []
                    for partner in st.session_state.tagged_partners:
                        out_path = local_store.send_to_partner(
                            new_sheet, partner, len(st.session_state.hearing_sheet_history)
                        )
                        st.session_state.partner_sent_at[partner] = os.path.getmtime(out_path)
                        out_paths.append((partner, out_path))
                lines = [render_hearing_sheet_md(new_sheet, "(đã soạn lại)"), "\nĐã gửi lại tới:"]
                for partner, path in out_paths:
                    lines.append(f"- {partner}: `{path}`")
                ss.add_message("assistant", "\n".join(lines))
                ss.set_step(ss.STEP_WAIT_PARTNER)
                st.rerun()

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

        elif step == ss.STEP_REPORT_REVIEW:
            approve = st.button("OK - Hoàn tất báo cáo", use_container_width=True)
            feedback = st.chat_input("Hoặc nhập góp ý để viết lại báo cáo...")

            if approve:
                ss.add_message("user", "OK - Hoàn tất báo cáo")
                ss.add_message("assistant", "Báo cáo đã hoàn tất. Cảm ơn Auditor đã sử dụng RIKAI.")
                ss.set_step(ss.STEP_DONE)
                st.rerun()
            elif feedback:
                ss.add_message("user", feedback)
                memory = ss.ensure_memory(st.session_state.session_id, st.session_state.partner)
                memory.add("report_feedback", feedback)
                with st.spinner("Đang viết lại báo cáo..."):
                    report = generate_report(
                        ss.current_hearing_sheet(), auditor_notes="",
                        previous_report=ss.current_report(), revision_feedback=feedback,
                    )
                    st.session_state.report_history.append(report)
                ss.add_message("assistant", render_report_md(report))
                st.rerun()

        elif step == ss.STEP_DONE:
            st.success("Phiên làm việc đã hoàn tất.")
            report = ss.current_report()
            if report:
                st.download_button("Tải báo cáo (Markdown)", data=report, file_name="rikai_report.md", mime="text/markdown")


def run():
    ss.init_state()

    st.title("RIKAI - Trợ lý khảo sát & viết báo cáo")
    st.caption("Auditor luôn là người review và xác nhận kết quả cuối cùng ở mỗi bước.")

    with st.sidebar:
        st.subheader("Phiên làm việc")
        if st.session_state.session_id:
            st.write(f"ID: `{st.session_state.session_id}`")
        if st.session_state.tagged_partners:
            st.write(f"Partner đang chờ: `{', '.join(st.session_state.tagged_partners)}`")
        if st.button("Bắt đầu phiên mới"):
            ss.reset_all()
            st.rerun()

    names = st.session_state.partner_names
    tab_auditor, tab_a, tab_b = st.tabs(
        ["Auditor", f"Partner: {names.get('a', 'Partner A')}", f"Partner: {names.get('b', 'Partner B')}"]
    )

    with tab_auditor:
        _render_auditor_tab()
    with tab_a:
        _render_partner_tab("a")
    with tab_b:
        _render_partner_tab("b")