"""
KPI Cards: top-level metric cards shown on the Overview and Code Quality pages.

Renders total events, active repos, unique contributors, GitPulse score,
PR merge rate, and issue close rate using st.metric.
"""

from __future__ import annotations

import streamlit as st
from streamlit.delta_generator import DeltaGenerator


def render(kpis: dict[str, int | float | None]) -> None:
    """Render the at-a-glance KPI cards."""
    row1: list[DeltaGenerator] = st.columns(spec=4)
    with row1[0]:
        st.metric(
            label=":material/inventory: Total events",
            value=f"{int(kpis.get('total_events') or 0):,}",
            help="Total events in the selected date range.",
            border=True,
        )
    with row1[1]:
        st.metric(
            label=":material/folder: Active repos",
            value=f"{int(kpis.get('active_repos') or 0):,}",
            help="Number of unique repositories with activity.",
            border=True,
        )
    with row1[2]:
        contributors = kpis.get("unique_contributors")
        st.metric(
            label=":material/group: Unique contributors",
            value=f"{int(contributors):,}" if contributors is not None else "N/A",
            help="Unique contributors in the selected period.",
            border=True,
        )
    with row1[3]:
        score = kpis.get("avg_gitpulse_score")
        st.metric(
            label=":material/star: GitPulse score",
            value=f"{score:.1f}" if score is not None else "N/A",
            help="Average GitPulse score across active repositories.",
            border=True,
        )
