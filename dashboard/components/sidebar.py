"""
Sidebar: global date range filter for all dashboard pages.

Renders a date input picker, the data freshness banner, and an apply button
shared across every page.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from dashboard.queries import get_date_range

_DATE_RANGE_LEN = 2
_FILTER_KEYS: list[str] = ["filter_date_range", "filter_date_range_picker"]


def _init_filters() -> tuple[date, date]:
    """Initialize session state with confirmed filter defaults."""
    if "filter_date_range" not in st.session_state:
        min_day, max_day = get_date_range()
        default_start = max(min_day, max_day - timedelta(days=30))
        st.session_state.filter_date_range = (default_start, max_day)
    return st.session_state.filter_date_range


def render() -> None:
    """Render sidebar filters. Call once in the entrypoint before navigation."""
    min_day, max_day = get_date_range()

    # Ensure confirmed filter exists
    confirmed: tuple[date, date] = _init_filters()

    st.sidebar.subheader(body="Global filters")
    st.sidebar.caption(body="Use these filters across every page.")

    # Picker widget: separate key so changing dates doesn't update the
    # confirmed filter and trigger expensive re-queries on every interaction.
    selected = st.sidebar.date_input(
        label=":material/calendar_month: Date range",
        value=confirmed,
        min_value=min_day,
        max_value=max_day,
        key="filter_date_range_picker",
    )

    st.sidebar.caption(body=f"Data up to **{max_day.isoformat()}** (freshness).")

    # Apply button: only on click does the confirmed filter update + rerun
    if st.sidebar.button(
        label="Apply",
        type="primary",
        width="stretch",
        icon=":material/filter_list:",
    ):
        if isinstance(selected, (list, tuple)) and len(selected) == _DATE_RANGE_LEN:
            st.session_state.filter_date_range: tuple[date, date] = (selected[0], selected[1])
            st.rerun()
        else:
            st.sidebar.warning(
                body="Select a start **and** end date for the range.",
                icon=":material/calendar_month:",
            )
    st.sidebar.divider()
    st.sidebar.caption(
        body=":material/bar_chart: Gitpulse Analytics turns GitHub's event stream into a diagnostic of the open-source world."
    )
    st.sidebar.link_button(
        label=":material/open_in_new: View project on GitHub",
        url="https://github.com/geogabrielp/gitpulse-analytics",
        type="secondary",
        use_container_width=True,
    )
    st.sidebar.button(
        label="Made with ❤️ by @geogabrielp",
        type="tertiary",
        use_container_width=True,
    )
