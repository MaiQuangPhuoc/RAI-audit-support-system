"""
Giao diện chat chính RIKAI.

Bố cục:
- Sidebar gốc của Streamlit (trái ngoài cùng, thu gọn được): thông tin
  "Phiên" (ID phiên, Partner đang chờ, bước hiện tại) + nút bắt đầu phiên mới.
- Tab "Auditor": cột trái (rộng) là khung chat kiểu tin nhắn (bong bóng
  trái/phải - tin của Auditor bên phải, của AI bên trái), cột phải là panel
  "Tài liệu" (file Auditor đã đính kèm).
- Tab "Partner A" / "Partner B": khung chat kiểu Zalo - tin/file của CHÍNH
  Partner đó (đã gửi) bên phải, tin/file từ Auditor (nhận được) bên trái.
  Partner bấm "Mở & điền trực tiếp" dưới file nhận được để điền ngay trên UI
  (giữ đúng cấu trúc cột gốc Auditor gửi, không cần tải xuống), có nút Lưu
  (giữ nháp), Hủy (đóng không lưu), và Xác nhận gửi lại cho Auditor.

GIỚI HẠN:
- Streamlit không hỗ trợ kéo-thả đổi độ rộng cột bằng chuột.
- Chỉ có 1 sidebar thật (bên trái) — không thể có sidebar thứ 2 ở bên phải,
  nên panel "Tài liệu" được làm bằng 1 cột thường bên phải khung chat, không
  phải sidebar thật.
- Bong bóng chat dùng st.container(border=True) đặt lệch trái/phải để mô
  phỏng dáng tin nhắn, không phải màu nền như Zalo thật. Muốn giống 100%
  cần custom component (React) - ngoài phạm vi prototype.
"""
import glob
import os
from datetime import datetime
import sys , os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import pandas as pd
import streamlit as st

from agents.analysis_agent import analyze_partner_answers
from agents.hearing_sheet_agent import create_hearing_sheet, revise_hearing_sheet, summarize_understanding
from agents.report_agent import generate_report
from core.schemas import HearingSheet, SheetTable
from ingestion.intake import extract_files_text, parse_tagged_partners
from storage import local_store
from ui import session_state as ss
from ui.render import (
    render_analysis_md,
    render_hearing_sheet_md,
    render_report_md,
    render_understanding_md,
    split_numbered_points,
)

st.set_page_config(page_title="RIKAI - Tro ly kiem toan", page_icon="📋", layout="wide")


def _bubble(role: str, content: str, user_side: str = "right", extra_render=None):
    """Vẽ 1 tin nhắn/file dạng bong bóng. user_side="right" (mặc định, dùng
    thống nhất cho cả Auditor lẫn Partner): role 'user' (chính chủ tab đang
    xem) hiện bên phải, 'assistant' (phía còn lại) hiện bên trái - đúng quy
    ước chat thông thường (Zalo/Messenger: tin của mình luôn bên phải)."""
    is_user = role == "user"
    show_right = (is_user and user_side == "right") or (not is_user and user_side == "left")
    if show_right:
        _, col = st.columns([1, 3])
    else:
        col, _ = st.columns([3, 1])
    with col:
        with st.container(border=True):
            st.markdown(content)
            if extra_render:
                extra_render()


def _replay_chat_log(user_side: str = "right"):
    for msg in st.session_state.chat_log:
        _bubble(msg["role"], msg["content"], user_side=user_side)


def _save_uploads(uploaded_files, subfolder: str) -> list[str]:
    return [local_store.save_uploaded_file(uf.getvalue(), uf.name, subfolder) for uf in (uploaded_files or [])]


def _render_editable_tables(sheet: HearingSheet, key_prefix: str) -> HearingSheet:
    edited_tables = []
    for ti, table in enumerate(sheet.tables):
        st.markdown(f"**Sheet: {table.sheet_name}**")
        if table.notes.strip():
            st.caption(f"Ghi chú/Tiêu chí: {table.notes}")

        columns = table.columns or ["Cột 1"]
        rows_data = [{c: row.get(c, "") for c in columns} for row in table.rows]
        df = pd.DataFrame(rows_data, columns=columns)

        column_config = {c: st.column_config.TextColumn(c, width="medium") for c in columns}
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"{key_prefix}_editor_{ti}",
            column_config=column_config,
        )
        new_rows = []
        for _, r in edited_df.iterrows():
            row_dict = {c: (str(r[c]).strip() if pd.notna(r[c]) else "") for c in columns}
            if any(v for v in row_dict.values()):
                new_rows.append(row_dict)
        edited_tables.append(SheetTable(sheet_name=table.sheet_name, notes=table.notes, columns=columns, rows=new_rows))

    return HearingSheet(title=sheet.title, tables=edited_tables, notes=sheet.notes)


def _render_understanding_points_interactive():
    """Hiển thị từng điểm trong 'Cách Agent hiểu nội dung' kèm icon bấm để mở
    ô trả lời RIÊNG cho đúng điểm đó — thay vì Auditor phải gõ hết vào 1 ô
    chat chung. Câu trả lời của từng điểm được lưu theo key riêng trong
    session_state, gộp lại khi Auditor gửi xác nhận ở ô chat bên dưới."""
    points = st.session_state.understanding_points
    if not points:
        return
    st.markdown("**🧠 Cách Agent hiểu nội dung — bấm 💬 để trả lời riêng từng điểm:**")
    icons = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, point in enumerate(points):
        icon = icons[i] if i < len(icons) else f"({i + 1})"
        col_point, col_toggle = st.columns([0.92, 0.08])
        with col_point:
            st.markdown(f"{icon} {point}")
        with col_toggle:
            st.checkbox("💬", key=f"toggle_point_{i}", label_visibility="collapsed")
        if st.session_state.get(f"toggle_point_{i}"):
            st.text_input(
                "Trả lời riêng cho điểm này",
                key=f"point_answer_{i}",
                placeholder="Trả lời/làm rõ riêng cho điểm này...",
                label_visibility="collapsed",
            )


def _collect_point_answers_text() -> str:
    """Gộp toàn bộ câu trả lời riêng-từng-điểm (nếu có) thành 1 đoạn text để
    đưa vào feedback chung gửi cho revise_hearing_sheet."""
    points = st.session_state.understanding_points
    parts = []
    for i, point in enumerate(points):
        ans = st.session_state.get(f"point_answer_{i}", "")
        if ans and ans.strip():
            parts.append(f"- Điểm {i + 1} ({point}): {ans.strip()}")
    return "\n".join(parts)


def _clear_point_answers():
    """Xoá toàn bộ trạng thái trả lời-riêng-từng-điểm (khi đã gửi xong hoặc
    chuyển sang Hearing Sheet mới), tránh câu trả lời cũ lẫn sang vòng sau."""
    for key in list(st.session_state.keys()):
        if key.startswith("toggle_point_") or key.startswith("point_answer_"):
            del st.session_state[key]
    st.session_state.understanding_points = []


def _render_docs_tab():
    docs = st.session_state.uploaded_docs
    if not docs:
        st.caption("Chưa có tài liệu nào được đính kèm.")
        return
    for doc in docs:
        path = doc["path"]
        if not os.path.exists(path):
            continue
        with st.expander(doc["name"], expanded=False):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                st.download_button("Tải xuống", data=data, file_name=doc["name"], key=f"dl_doc_{doc['name']}_{path}")
            except Exception as e:
                st.caption(f"Không đọc được file: {e}")


def _render_session_tab():
    if st.session_state.session_id:
        st.write(f"ID phiên: `{st.session_state.session_id}`")
    else:
        st.caption("Chưa bắt đầu phiên nào.")
    if st.session_state.tagged_partners:
        st.write(f"Partner đang chờ: `{', '.join(st.session_state.tagged_partners)}`")
    st.caption(f"Bước hiện tại: `{st.session_state.step}`")


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

    open_key = f"open_file_{key}"
    draft_key = f"draft_sheet_{key}"

    if not events:
        st.info(f"Chưa có khảo sát nào gửi tới {name}. Khi Auditor @{name} trong nội dung và gửi, file sẽ xuất hiện ở đây.")
    else:
        for kind, path in events:
            ts = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%H:%M:%S %d/%m")
            fname = os.path.basename(path)
            if kind == "received":
                content = f"📥 **Khảo sát nhận được** lúc {ts}\n\n📄 `{fname}`"

                def _open_btn(p=path):
                    if st.button("📂 Mở & điền trực tiếp", key=f"open_{key}_{p}", use_container_width=True):
                        st.session_state[open_key] = p
                        st.session_state.pop(draft_key, None)  # mở file khác -> đọc lại từ đầu
                        st.rerun()

                _bubble("assistant", content, user_side="right", extra_render=_open_btn)
            else:
                content = f"📤 **Đã gửi trả lời** lúc {ts}\n\n📄 `{fname}`"
                _bubble("user", content, user_side="right")

    # ---------------------------------------------------------------
    # Panel điền/sửa file đang mở (nếu có) — mở ngay trên UI, giữ đúng
    # nguyên cấu trúc cột Auditor đã gửi (đọc qua read_answered_xlsx, dùng
    # chung logic tách bảng/ghi chú đã kiểm chứng), không cần tải xuống.
    # ---------------------------------------------------------------
    open_path = st.session_state.get(open_key)
    if open_path and os.path.exists(open_path):
        st.divider()
        st.markdown(f"### ✏️ Đang điền: `{os.path.basename(open_path)}`")

        if draft_key not in st.session_state:
            st.session_state[draft_key] = local_store.read_answered_xlsx(open_path)
        current_sheet = st.session_state[draft_key]

        edited_sheet = _render_editable_tables(current_sheet, key_prefix=f"partner_edit_{key}")

        col_save, col_cancel, col_confirm = st.columns([1, 1, 2])
        with col_save:
            if st.button("💾 Lưu", key=f"save_{key}", use_container_width=True):
                st.session_state[draft_key] = edited_sheet
                st.success("Đã lưu nháp — chưa gửi cho Auditor.")
        with col_cancel:
            if st.button("❌ Hủy", key=f"cancel_{key}", use_container_width=True):
                st.session_state.pop(open_key, None)
                st.session_state.pop(draft_key, None)
                st.rerun()
        with col_confirm:
            if st.button("✅ Xác nhận gửi lại cho Auditor", key=f"confirm_{key}", type="primary", use_container_width=True):
                edited_sheet.title = current_sheet.title
                dest_dir = local_store.inbox_path_for(name)
                dest_path = os.path.join(
                    dest_dir, f"reply_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                )
                local_store.export_hearing_sheet_xlsx(edited_sheet, dest_path)
                st.session_state.pop(open_key, None)
                st.session_state.pop(draft_key, None)
                st.success("Đã gửi trả lời cho Auditor.")
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
    col_chat, col_docs = st.columns([4, 1])

    with col_docs:
        st.markdown("#### 📁 Tài liệu")
        _render_docs_tab()

    with col_chat:
        _replay_chat_log(user_side="right")
        step = st.session_state.step

        if step == ss.STEP_INTAKE:
            names = st.session_state.partner_names
            _bubble(
                "assistant",
                f"Xin chào Auditor. Nhập nội dung khảo sát, đính kèm file nếu có "
                f"(PDF/XLSX), và @tên Partner ngay trong nội dung để chọn ai nhận "
                f"(VD: @{names.get('a', 'VendorA')}). Chỉ Partner được @ mới nhận khảo sát này.",
                user_side="right",
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

                    # Chỉ khi Auditor upload ĐÚNG 1 file XLSX (không kèm PDF), mới có "file gốc
                    # duy nhất" để gửi thẳng bản sao y hệt khi chưa có yêu cầu sửa gì.
                    is_single_xlsx = len(file_paths) == 1 and file_paths[0].lower().endswith((".xlsx", ".xlsm"))
                    st.session_state.original_file_path = file_paths[0] if is_single_xlsx else None
                    st.session_state.hearing_sheet_modified = False

                    with st.spinner("Đang bóc tách file và tạo Hearing Sheet..."):
                        sheet, warnings = create_hearing_sheet(
                            file_paths, content, title=f"Khảo sát {', '.join(tagged)}"
                        )
                        st.session_state.hearing_sheet_history.append(sheet)
                        local_store.save_hearing_sheet_json(sheet, session_id, version=1)
                        understanding = summarize_understanding(sheet)

                    reply = render_hearing_sheet_md(sheet, "(v1)")
                    if warnings:
                        reply += "\n\n**Cảnh báo:**\n" + "\n".join(f"- {w}" for w in warnings)
                    reply += "\n\n---\n" + render_understanding_md(understanding)

                    ss.add_message("assistant", reply)
                    st.session_state.understanding_points = split_numbered_points(understanding)
                    ss.set_step(ss.STEP_HEARING_SHEET_REVIEW)
                    st.rerun()

        elif step == ss.STEP_HEARING_SHEET_REVIEW:
            sheet = ss.current_hearing_sheet()

            _render_understanding_points_interactive()

            with st.expander("Chỉnh sửa bảng trực tiếp (thêm/sửa/xoá dòng)", expanded=False):
                edited_sheet = _render_editable_tables(sheet, key_prefix="hs_review")
                if st.button("Lưu chỉnh sửa bảng"):
                    edited_sheet.title = sheet.title
                    st.session_state.hearing_sheet_history.append(edited_sheet)
                    st.session_state.hearing_sheet_modified = True
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
            feedback = st.chat_input(
                "Nếu đã trả lời riêng từng điểm ở trên, chỉ cần gõ xác nhận (VD: OK) ở đây để gửi — "
                "hoặc gõ góp ý chung nếu muốn."
            )

            if approve:
                sheet = ss.current_hearing_sheet()
                ss.add_message("user", "OK - Gửi cho Partner")
                out_paths = []
                send_original = (not st.session_state.hearing_sheet_modified) and st.session_state.original_file_path
                with st.spinner("Đang gửi file cho Partner..."):
                    for partner in st.session_state.tagged_partners:
                        if send_original:
                            out_path = local_store.send_original_file_to_partner(
                                st.session_state.original_file_path, partner
                            )
                        else:
                            out_path = local_store.send_to_partner(
                                sheet, partner, version=len(st.session_state.hearing_sheet_history)
                            )
                        st.session_state.partner_sent_at[partner] = os.path.getmtime(out_path)
                        out_paths.append((partner, out_path))

                lines = [
                    "Đã gửi " + ("(bản gốc, chưa sửa gì)" if send_original else "(bản đã qua chỉnh sửa)")
                    + " tới:"
                ]
                for partner, path in out_paths:
                    lines.append(f"- {partner}: `{path}`")
                lines.append(
                    "\nSang tab của từng Partner để tải file, điền câu trả lời, rồi upload lại "
                    "ngay trong tab đó - hoặc hệ thống sẽ tự kiểm tra mỗi 60 giây."
                )
                ss.add_message("assistant", "\n".join(lines))
                _clear_point_answers()
                ss.set_step(ss.STEP_WAIT_PARTNER)
                st.rerun()

            elif feedback:
                point_answers_text = _collect_point_answers_text()
                combined_feedback = feedback.strip()
                if point_answers_text:
                    prefix = "Trả lời riêng từng điểm Auditor đã nhập trên UI:\n" + point_answers_text
                    combined_feedback = f"{prefix}\n\nGóp ý thêm: {combined_feedback}" if combined_feedback else prefix

                ss.add_message("user", combined_feedback)
                st.session_state.hearing_sheet_modified = True
                memory = ss.ensure_memory(st.session_state.session_id, st.session_state.partner)
                with st.spinner("Đang soạn lại Hearing Sheet theo góp ý..."):
                    new_sheet = revise_hearing_sheet(sheet, auditor_feedback=combined_feedback, memory=memory)
                    memory.add("hearing_sheet_feedback", combined_feedback)
                    st.session_state.hearing_sheet_history.append(new_sheet)
                    local_store.save_hearing_sheet_json(
                        new_sheet, st.session_state.session_id, len(st.session_state.hearing_sheet_history)
                    )
                _clear_point_answers()
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
        st.subheader("⚙️ Phiên")
        if st.button("🔄 Bắt đầu phiên mới"):
            ss.reset_all()
            st.rerun()
        st.divider()
        _render_session_tab()

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