"""Streamlit implementation of the time reproduction experiment.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

import streamlit as st


TARGET_DURATION_SECONDS = 7.0
ACTIVITY_OPTIONS = ("Studying", "Relaxing", "Social", "Traveling")
EVENT_OPTIONS = ("No", "Yes")
RESULT_COLUMNS = (
    "submitted_at",
    "time",
    "distortion",
    "stress",
    "activity",
    "event",
    "intensity",
)


def initialize_state() -> None:
    """Create all session state keys used by the app."""
    defaults: dict[str, Any] = {
        "step": 0,
        "focus_started_at": None,
        "start_time": None,
        "end_time": None,
        "reproduced_time": None,
        "stress": 3,
        "activity": ACTIVITY_OPTIONS[0],
        "stress_event": EVENT_OPTIONS[0],
        "intensity": 50,
        "submitted_result": None,
        "save_error": None,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_experiment() -> None:
    """Reset the app to the first experimental step."""
    st.session_state.step = 0
    st.session_state.focus_started_at = None
    st.session_state.start_time = None
    st.session_state.end_time = None
    st.session_state.reproduced_time = None
    st.session_state.submitted_result = None
    st.session_state.save_error = None


def centered_container() -> None:
    """Apply lightweight styling for a clean centered layout."""
    st.markdown(
        """
        <style>
            .block-container {
                max-width: 680px;
                padding-top: 4rem;
                padding-bottom: 4rem;
            }

            div.stButton > button {
                width: 100%;
                border-radius: 0.5rem;
                padding: 0.75rem 1rem;
                font-weight: 600;
            }

            .focus-circle {
                width: 120px;
                height: 120px;
                margin: 1.5rem auto 0 auto;
                border-radius: 50%;
                background: #2563eb;
            }

            .metric-box {
                text-align: center;
                padding: 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 0.5rem;
                background: #ffffff;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_step_header(label: str, progress_value: float) -> None:
    """Render the current step label and progress bar."""
    st.caption(label)
    st.progress(progress_value)


def render_home_step() -> None:
    """Show participant instructions before the experiment begins."""
    st.title("Time Estimation Task")
    st.write(
        "In this task, you will first look at a circle for a short amount of time. "
        "After that, you will try to reproduce the same duration yourself."
    )
    st.write(
        "When the reproduction screen appears, wait until you feel the same amount "
        "of time has passed, then press **Release**."
    )
    st.info("Please stay focused on the circle and avoid counting seconds.")

    if st.button("Start experiment"):
        st.session_state.step = 1
        st.session_state.focus_started_at = None
        st.rerun()


def render_focus_step() -> None:
    """Step 1: display the focus circle for seven seconds."""
    render_step_header("Step 1 of 3: Focus", 1 / 3)
    st.title("Focus on the circle")
    st.markdown('<div class="focus-circle"></div>', unsafe_allow_html=True)

    if st.session_state.focus_started_at is None:
        st.session_state.focus_started_at = time.monotonic()

    elapsed = time.monotonic() - st.session_state.focus_started_at
    remaining = max(0.0, TARGET_DURATION_SECONDS - elapsed)

    if remaining > 0:
        # Streamlit reruns after this sleep, giving the user a timed focus screen.
        time.sleep(min(remaining, 0.25))
        st.rerun()

    st.session_state.step = 2
    st.rerun()


def render_reproduction_step() -> None:
    """Step 2: measure the reproduced duration."""
    render_step_header("Step 2 of 3: Reproduce", 2 / 3)
    st.title("Reproduce the duration")
    st.write("Wait for the same duration you just observed, then press **Release**.")

    if st.session_state.start_time is None:
        st.session_state.start_time = time.monotonic()
        st.session_state.end_time = None

    if st.button("Release"):
        st.session_state.end_time = time.monotonic()
        st.session_state.reproduced_time = (
            st.session_state.end_time - st.session_state.start_time
        )
        st.session_state.step = 3
        st.rerun()


def google_sheets_is_configured() -> bool:
    """Return whether the Streamlit secrets needed for Google Sheets exist."""
    try:
        return "gcp_service_account" in st.secrets and "google_sheet_id" in st.secrets
    except FileNotFoundError:
        return False


@st.cache_resource(show_spinner=False)
def get_google_worksheet(
    _service_account_info: dict[str, str],
    sheet_id: str,
    worksheet_name: str,
):
    """Connect to the configured Google Sheet worksheet."""
    import gspread

    credentials = dict(_service_account_info)
    credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")

    client = gspread.service_account_from_dict(credentials)
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.worksheet(worksheet_name)


def save_result_to_google_sheets(result: dict[str, float | int | str]) -> None:
    """Append one experiment result row to Google Sheets."""
    if not google_sheets_is_configured():
        raise RuntimeError("Google Sheets is not configured yet.")

    worksheet_name = st.secrets.get("worksheet_name", "Sheet1")
    worksheet = get_google_worksheet(
        st.secrets["gcp_service_account"],
        st.secrets["google_sheet_id"],
        worksheet_name,
    )

    # Create the header row if the sheet is empty.
    if not worksheet.row_values(1):
        worksheet.append_row(list(RESULT_COLUMNS))

    worksheet.append_row([result[column] for column in RESULT_COLUMNS])


def build_result_payload() -> dict[str, float | int | str]:
    """Build the final result dictionary from session state."""
    reproduced_time = float(st.session_state.reproduced_time or 0.0)

    return {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "time": reproduced_time,
        "distortion": reproduced_time - TARGET_DURATION_SECONDS,
        "stress": int(st.session_state.stress),
        "activity": st.session_state.activity,
        "event": st.session_state.stress_event,
        "intensity": int(st.session_state.intensity),
    }


def render_ema_step() -> None:
    """Step 3: collect EMA inputs and show/store the final result."""
    render_step_header("Step 3 of 3: EMA", 1.0)
    st.title("EMA Check-in")

    reproduced_time = float(st.session_state.reproduced_time or 0.0)
    distortion = reproduced_time - TARGET_DURATION_SECONDS

    st.metric("Reproduced time", f"{reproduced_time:.2f} sec", f"{distortion:+.2f} sec")

    with st.form("ema_form"):
        st.session_state.stress = st.slider(
            "Current stress",
            min_value=1,
            max_value=5,
            value=int(st.session_state.stress),
            step=1,
        )
        st.session_state.activity = st.selectbox(
            "Activity",
            options=ACTIVITY_OPTIONS,
            index=ACTIVITY_OPTIONS.index(st.session_state.activity),
        )
        st.session_state.stress_event = st.selectbox(
            "Stress event occurred",
            options=EVENT_OPTIONS,
            index=EVENT_OPTIONS.index(st.session_state.stress_event),
        )
        st.session_state.intensity = st.slider(
            "Stress intensity",
            min_value=0,
            max_value=100,
            value=int(st.session_state.intensity),
            step=1,
        )

        submitted = st.form_submit_button("Submit")

    if submitted:
        result = build_result_payload()
        st.session_state.submitted_result = result
        st.session_state.save_error = None

        try:
            save_result_to_google_sheets(result)
        except Exception as exc:
            st.session_state.save_error = str(exc)

        print(result)

    if st.session_state.submitted_result is not None:
        if st.session_state.save_error is None:
            st.success("Result saved to Google Sheets.")
        else:
            st.warning("Result stored for this session, but Google Sheets did not save it yet.")
            st.caption(st.session_state.save_error)

        st.json(st.session_state.submitted_result)

    st.button("Run again", on_click=reset_experiment)


def main() -> None:
    """Run the Streamlit app."""
    st.set_page_config(
        page_title="Time Reproduction Task",
        page_icon="timer",
        layout="centered",
    )
    initialize_state()
    centered_container()

    if st.session_state.step == 0:
        render_home_step()
    elif st.session_state.step == 1:
        render_focus_step()
    elif st.session_state.step == 2:
        render_reproduction_step()
    else:
        render_ema_step()


if __name__ == "__main__":
    main()
