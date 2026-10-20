"""
Organizations: aggregated metrics per organization.

Uses streamlit_echarts for bar charts.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from polars import DataFrame
from streamlit_echarts import st_echarts

from dashboard.components._palette import PRIMARY, SUCCESS, VIOLET


def render_org_summary(org_summary: DataFrame) -> None:
    """Top 10 orgs bar chart (full-width) + expandable top 100 orgs table."""
    if org_summary.is_empty():
        st.info(body="No organization data for the current selection.")
        return

    top10: DataFrame = org_summary.head(n=10)
    top100: DataFrame = org_summary.head(n=100)

    names: list[Any] = top10["org_name"].to_list()[::-1]
    events: list[Any] = top10["total_events"].to_list()[::-1]
    repos: list[Any] = top10["active_repos"].to_list()[::-1]
    scores: list[Any] = top10["avg_gitpulse_score"].to_list()[::-1]

    options = {
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
        },
        "grid": {"left": "3%", "right": "8%", "bottom": "3%", "containLabel": True},
        "xAxis": {"type": "value", "minInterval": 1},
        "yAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"fontSize": 11},
        },
        "series": [
            {
                "name": "Total events",
                "type": "bar",
                "data": events,
                "itemStyle": {"color": PRIMARY, "borderRadius": [0, 4, 4, 0]},
                "barWidth": "60%",
            },
            {
                "name": "Active repos",
                "type": "bar",
                "data": repos,
                "itemStyle": {"color": SUCCESS, "borderRadius": [0, 4, 4, 0]},
                "emphasis": {"itemStyle": {"opacity": 0}},
                "silent": True,
                "barWidth": "60%",
                "barGap": "-100%",
                "z": -1,
            },
            {
                "name": "Avg GitPulse score",
                "type": "bar",
                "data": scores,
                "itemStyle": {"color": VIOLET, "borderRadius": [0, 4, 4, 0]},
                "emphasis": {"itemStyle": {"opacity": 0}},
                "silent": True,
                "barWidth": "60%",
                "barGap": "-100%",
                "z": -1,
            },
        ],
    }
    st_echarts(options, height="360px")

    with st.expander(label=":material/table: View full table (top 100 organizations)"):
        df_display = top100.to_pandas().rename(
            columns={
                "org_name": "Organization",
                "total_events": "Total events",
                "active_repos": "Active repos",
                "avg_gitpulse_score": "Avg GitPulse score",
            }
        )
        st.dataframe(data=df_display, width="stretch", hide_index=True)
        st.download_button(
            label=":material/download: Download CSV",
            data=df_display.to_csv(index=False),
            file_name="organizations.csv",
            mime="text/csv",
            width="stretch",
            key="org_csv",
        )
