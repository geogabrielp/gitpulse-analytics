"""Code Quality: PRs, issues, code review engagement, and score trends."""

from __future__ import annotations

from typing import Any, cast

import streamlit as st
from polars.dataframe.frame import DataFrame
from streamlit.delta_generator import DeltaGenerator

from dashboard.components.activity_trends import (
    render_score_timeline,
)
from dashboard.components.issues import (
    render_issue_close_rate,
    render_issues_opened_vs_closed,
)
from dashboard.components.pr_health import (
    render_pr_bot_comparison,
    render_pr_funnel,
    render_pr_merge_rate,
    render_pr_opened_vs_merged,
)
from dashboard.components.review_health import (
    render_comments_per_pr,
    render_reviews_comments_per_day,
    render_reviews_per_pr,
)
from dashboard.queries import (
    get_code_review_metrics,
    get_daily_event_breakdown,
    get_issue_metrics,
    get_pr_bot_breakdown,
    get_pr_metrics,
)

st.title(body=":material/code: Code Quality")
st.markdown(body="Pull requests, issues, code review engagement, and GitPulse score trends.")

# Date validation
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

# Data loading
progress_holder: DeltaGenerator = st.empty()

try:
    with progress_holder.container():
        bar: DeltaGenerator = st.progress(value=0, text="Fetching PR metrics…")
        pr_metrics: DataFrame = get_pr_metrics(start=start, end=end)

        bar.progress(value=20, text="Loading PR bot breakdown…")
        pr_bot_data: DataFrame = get_pr_bot_breakdown(start=start, end=end)

        bar.progress(value=40, text="Fetching issue metrics…")
        issue_metrics: DataFrame = get_issue_metrics(start=start, end=end)

        bar.progress(value=60, text="Loading review metrics…")
        review_data: DataFrame = get_code_review_metrics(start=start, end=end)

        bar.progress(value=80, text="Loading score timeline…")
        breakdown: DataFrame = get_daily_event_breakdown(start=start, end=end)

        bar.progress(value=100, text=":material/check_circle: Ready!")
except Exception:
    progress_holder.empty()
    st.error(body="Failed to load code quality data. Check that the data source is available.")
    st.stop()

progress_holder.empty()

# Period averages
merge_rate_mean = pr_metrics["avg_merge_rate"].mean() if not pr_metrics.is_empty() else None
close_rate_mean = issue_metrics["avg_close_rate"].mean() if not issue_metrics.is_empty() else None
overall_merge_rate = float(cast(float, merge_rate_mean)) if merge_rate_mean is not None else None
overall_close_rate = float(cast(float, close_rate_mean)) if close_rate_mean is not None else None

# Compute review totals for the top cards
if not review_data.is_empty():
    _total_reviews = int(review_data["review_events"].sum())
    _total_comments = int(review_data["comment_events"].sum())
    _total_prs = int(review_data["pr_events"].sum())
    _overall_reviews_pr = (
        round(number=_total_reviews / _total_prs, ndigits=2) if _total_prs > 0 else None
    )
    _overall_comments_pr = (
        round(number=_total_comments / _total_prs, ndigits=2) if _total_prs > 0 else None
    )
else:
    _total_reviews = _total_comments = _total_prs = 0
    _overall_reviews_pr = _overall_comments_pr = None

# Top metric cards
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric(
        label="Total reviews",
        value=f"{_total_reviews:,}",
        help="Number of pull request review events in the period.",
        border=True,
    )
with m2:
    st.metric(
        label="Total comments",
        value=f"{_total_comments:,}",
        help="Number of issue or PR comment events in the period.",
        border=True,
    )
with m3:
    st.metric(
        label="Overall reviews/PR",
        value=f"{_overall_reviews_pr:.2f}x" if _overall_reviews_pr is not None else "N/A",
        help="Average number of reviews per pull request across the period.",
        border=True,
    )
with m4:
    st.metric(
        label="Overall comments/PR",
        value=f"{_overall_comments_pr:.2f}x" if _overall_comments_pr is not None else "N/A",
        help="Average number of comments per pull request across the period.",
        border=True,
    )

st.divider()

col1, col2 = st.columns(spec=2)
with col1:
    st.subheader(body=":material/lock_open: **PRs opened vs merged**")
    st.markdown(body="Daily opened and merged pull requests.")
    render_pr_opened_vs_merged(pr_metrics)
with col2:
    st.subheader(body=":material/check_circle: **PR merge rate**")
    st.markdown(body="Percentage of PRs merged each day.")
    render_pr_merge_rate(pr_metrics, overall_mean=overall_merge_rate)

st.divider()

col3, col4 = st.columns(spec=2)
with col3:
    st.subheader(body=":material/repeat: **PR funnel: Opened → Merged**")
    st.markdown(body="Conversion breakdown from opened to merged.")
    render_pr_funnel(pr_metrics)
with col4:
    st.subheader(body=":material/smart_toy: **PRs by bot vs human**")
    st.markdown(body="Pull request authorship split by actor type.")
    render_pr_bot_comparison(pr_bot_data)
st.divider()

col5, col6 = st.columns(spec=2)
with col5:
    st.subheader(body=":material/edit_note: **Issues opened vs closed**")
    st.markdown(body="Daily opened and closed issues.")
    render_issues_opened_vs_closed(issue_metrics)
with col6:
    st.subheader(body=":material/check_circle: **Issue close rate**")
    st.markdown(body="Percentage of issues closed each day.")
    render_issue_close_rate(issue_metrics, overall_mean=overall_close_rate)
st.divider()

st.subheader(body=":material/rate_review: **Reviews & Comments per day**")
st.markdown(body="Daily review and comment events.")
render_reviews_comments_per_day(review_data)
st.divider()

col7, col8 = st.columns(spec=2)
with col7:
    st.subheader(body=":material/feedback: **Reviews per PR**")
    st.markdown(body="Average reviews per pull request.")
    render_reviews_per_pr(review_data)
with col8:
    st.subheader(body=":material/comment: **Comments per PR**")
    st.markdown(body="Average comments per pull request.")
    render_comments_per_pr(review_data)
st.divider()

st.subheader(body=":material/trending_up: GitPulse Score over time")
st.markdown(body="Average daily GitPulse Score across active repositories.")
render_score_timeline(breakdown)
