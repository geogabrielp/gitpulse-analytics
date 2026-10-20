"""Community & Activity: contributor rankings, bot vs human, and activity heatmap."""

from __future__ import annotations

from typing import Any

import streamlit as st
from polars.dataframe.frame import DataFrame
from streamlit.delta_generator import DeltaGenerator

from dashboard.components.community import (
    render_bot_vs_human,
    render_contributors_over_time,
    render_daily_heatmap,
    render_events_bot_vs_human_over_time,
    render_top_contributors,
)
from dashboard.queries import (
    get_bot_vs_human,
    get_contributors_over_time,
    get_daily_heatmap,
    get_top_contributors,
)

st.title(body=":material/group: Community & Activity")
st.markdown(body="Contributor behaviour, bot activity, and when work happens.")

# date validation
date_range: Any | None = st.session_state.get("filter_date_range")

if not date_range or not isinstance(date_range, (list, tuple)) or len(date_range) != 2:  # noqa: PLR2004
    st.info(
        body="Select a complete date range in the sidebar.",
        icon=":material/calendar_month:",
    )
    st.stop()

start, end = date_range

if start > end:
    st.error(body="Start date must be on or before end date.")
    st.stop()

# data loading
progress_holder: DeltaGenerator = st.empty()

try:
    with progress_holder.container():
        bar: DeltaGenerator = st.progress(value=0, text="Loading bot vs human…")
        bot_data: DataFrame = get_bot_vs_human(start=start, end=end)

        bar.progress(value=20, text="Fetching top contributors…")
        contributors: DataFrame = get_top_contributors(start=start, end=end)

        bar.progress(value=40, text="Building contributor timeline…")
        contributors_ts: DataFrame = get_contributors_over_time(start=start, end=end)

        bar.progress(value=60, text="Loading push event heatmap…")
        push_heatmap: DataFrame = get_daily_heatmap(end=end, event_type="PushEvent")

        bar.progress(value=80, text="Loading PR event heatmap…")
        pr_heatmap: DataFrame = get_daily_heatmap(end=end, event_type="PullRequestEvent")

        bar.progress(value=100, text=":material/check_circle: Ready!")
except Exception:
    progress_holder.empty()
    st.error(body="Failed to load community data. Check that the data source is available.")
    st.stop()

progress_holder.empty()

# Render sections
st.subheader(body=":material/local_fire_department: Daily activity heatmap")
st.markdown(
    body="Event concentration by day-of-week and hour (reveals peak activity windows).",
    help="Always shows the last 7 days ending on the selected end date.",
)

tab_push, tab_pr = st.tabs(
    tabs=[
        ":material/code: Push Events",
        ":material/call_split: PR Events",
    ]
)

with tab_pr:
    render_daily_heatmap(pr_heatmap, color_scheme="blue")
with tab_push:
    render_daily_heatmap(push_heatmap, color_scheme="green")

st.divider()

col1, col2 = st.columns(spec=2)
with col1:
    st.subheader(body=":material/smart_toy: Humans vs Bots")
    st.markdown(body="Overall split of events by actor type.")
    render_bot_vs_human(bot_data)
with col2:
    st.subheader(body=":material/trending_up: Events by bot vs human")
    st.markdown(body="Daily event count split between automated bots and humans.")
    render_events_bot_vs_human_over_time(bot_data)
st.caption(
    body="**Note:** LLMs using personal accounts (Copilot, Cody, Cursor) are "
    "invisible in this data. Only bots with dedicated accounts "
    "(e.g. `cursor[bot]`) are captured."
)
st.divider()

st.subheader(body=":material/emoji_events: Top contributors")
st.markdown(body="Most active contributors by events, repos, and PRs split by actor type.")
render_top_contributors(contributors)
st.divider()

st.subheader(body=":material/group: Contributors over time")
st.markdown(body="Unique human and bot contributors per day.")
render_contributors_over_time(contributors_ts)
