"""State machine luồng nghiệp vụ RIKAI trong 1 phiên Streamlit."""
import streamlit as st

STEP_INTAKE = "INTAKE"
STEP_HEARING_SHEET_REVIEW = "HEARING_SHEET_REVIEW"
STEP_WAIT_PARTNER = "WAIT_PARTNER"
STEP_ANALYSIS_REVIEW = "ANALYSIS_REVIEW"
STEP_REPORT_INPUT = "REPORT_INPUT"
STEP_REPORT_REVIEW = "REPORT_REVIEW"
STEP_DONE = "DONE"


def init_state():
    defaults = {
        "step": STEP_INTAKE,
        "chat_log": [],
        "session_id": None,
        "partner": None,
        "hearing_sheet_history": [],   # list[HearingSheet]
        "analysis_history": [],        # list[AnalysisResult]
        "report_history": [],          # list[str] markdown
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def current_hearing_sheet():
    return st.session_state.hearing_sheet_history[-1] if st.session_state.hearing_sheet_history else None


def current_analysis():
    return st.session_state.analysis_history[-1] if st.session_state.analysis_history else None


def current_report():
    return st.session_state.report_history[-1] if st.session_state.report_history else None


def add_message(role: str, content: str):
    st.session_state.chat_log.append({"role": role, "content": content})


def set_step(step: str):
    st.session_state.step = step


def reset_all():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()
