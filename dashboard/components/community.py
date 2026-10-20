"""
Community & Actors: contributor rankings, bot vs human activity, and trends.

Uses streamlit_echarts for bar, line, and dual line charts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pandas.core.frame
import streamlit as st
from polars import DataFrame
from streamlit_echarts import st_echarts

from dashboard.components._palette import BOT, HUMAN, PRIMARY


def _stacked_contributor_chart(data: DataFrame, is_bot_group: bool) -> None:
    """Stacked horizontal bar: events / repos / PRs per contributor."""
    if data.is_empty():
        st.info(body=f"No {'bot' if is_bot_group else 'human'} contributors found.")
        return

    top: DataFrame = data.head(n=10)
    names: list[Any] = top["login"].to_list()[::-1]

    events_vals: list[Any] = top["events"].to_list()[::-1]
    repos_vals: list[Any] = top["repos"].to_list()[::-1]
    prs_vals: list[Any] = top["prs"].to_list()[::-1]

    # Three shades per hue — lightest for events, darkest for PRs
    if is_bot_group:
        ev_color = "#FDBA74"
        rp_color = "#F97316"
        pr_color = "#EA580C"
    else:
        ev_color = "#93C5FD"
        rp_color = "#60A5FA"
        pr_color = "#3B82F6"

    options = {
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "formatter": (
                "{b}<br/>"
                f'<span style="color:{ev_color}">●</span> Events: {{c0}}<br/>'
                f'<span style="color:{rp_color}">●</span> Repos: {{c1}}<br/>'
                f'<span style="color:{pr_color}">●</span> PRs: {{c2}}'
            ),
        },
        "legend": {"data": ["Events", "Repos", "PRs"], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {"type": "value", "minInterval": 1},
        "yAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"fontSize": 11},
            "inverse": False,
        },
        "series": [
            {
                "name": "Events",
                "type": "bar",
                "stack": "total",
                "data": events_vals,
                "itemStyle": {"color": ev_color, "borderRadius": [0, 0, 0, 0]},
                "barMaxWidth": 24,
            },
            {
                "name": "Repos",
                "type": "bar",
                "stack": "total",
                "data": repos_vals,
                "itemStyle": {"color": rp_color},
                "barMaxWidth": 24,
            },
            {
                "name": "PRs",
                "type": "bar",
                "stack": "total",
                "data": prs_vals,
                "itemStyle": {"color": pr_color, "borderRadius": [0, 4, 4, 0]},
                "barMaxWidth": 24,
            },
        ],
    }
    st_echarts(options, height="360px")


def render_top_contributors(contributors: DataFrame) -> None:
    """Tabs with stacked horizontal bar: top humans and top bots."""
    if contributors.is_empty():
        st.info(body="No contributor data for this period.")
        return

    humans: DataFrame = contributors.filter(~contributors["is_bot"])
    bots: DataFrame = contributors.filter(contributors["is_bot"])

    tab_h, tab_b = st.tabs(
        tabs=[
            ":material/face: Top Humans",
            ":material/smart_toy: Top Bots",
        ]
    )
    with tab_h:
        _stacked_contributor_chart(data=humans, is_bot_group=False)
    with tab_b:
        _stacked_contributor_chart(data=bots, is_bot_group=True)


def render_contributors_over_time(contributors_ts: DataFrame) -> None:
    """Dual line chart: unique human vs bot contributors per day, legend below."""
    if contributors_ts.is_empty():
        st.info(body="No contributor timeline data for this period.")
        return

    pdf = contributors_ts.to_pandas()
    pivoted = pdf.pivot_table(
        index="day", columns="is_bot", values="contributors", aggfunc="sum", fill_value=0
    ).sort_index()

    days = [d.strftime("%Y-%m-%d") for d in pivoted.index]
    human_vals: list[int] = [
        int(v) for v in pivoted.get(False, pd.Series(data=[0] * len(pivoted))).tolist()
    ]
    bot_vals: list[int] = [
        int(v) for v in pivoted.get(True, pd.Series(data=[0] * len(pivoted))).tolist()
    ]

    series = [
        {
            "name": "Human",
            "type": "line",
            "data": human_vals,
            "smooth": True,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": HUMAN},
            "areaStyle": {"opacity": 0.12},
        },
        {
            "name": "Bot",
            "type": "line",
            "data": bot_vals,
            "smooth": True,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": BOT},
            "areaStyle": {"opacity": 0.12},
        },
    ]

    options = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["Human", "Bot"], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "boundaryGap": False,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {"type": "value", "minInterval": 1},
        "series": series,
    }
    st_echarts(options, height="360px")


def render_events_bot_vs_human_over_time(bot_data: DataFrame) -> None:
    """Dual line chart (overlaid): events by bot vs human per day."""
    if bot_data.is_empty():
        st.info(body="No bot vs human data for this period.")
        return

    pdf = bot_data.to_pandas()
    pivoted = pdf.pivot_table(
        index="day", columns="is_bot", values="events", aggfunc="sum", fill_value=0
    ).sort_index()

    days = [d.strftime("%Y-%m-%d") for d in pivoted.index]
    human_events: list[int] = [
        int(v) for v in pivoted.get(key=False, default=pd.Series(data=[0] * len(pivoted))).tolist()
    ]
    bot_events: list[int] = [
        int(v) for v in pivoted.get(key=True, default=pd.Series(data=[0] * len(pivoted))).tolist()
    ]

    series = [
        {
            "name": "Human",
            "type": "line",
            "data": human_events,
            "smooth": True,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": HUMAN},
        },
        {
            "name": "Bot",
            "type": "line",
            "data": bot_events,
            "smooth": True,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": BOT},
        },
    ]

    options = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [s["name"] for s in series], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "boundaryGap": False,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {"type": "value", "minInterval": 1},
        "series": series,
    }
    st_echarts(options, height="360px")


def render_bot_vs_human(bot_data: DataFrame) -> None:
    """Donut chart: proportion of bot vs human events."""
    if bot_data.is_empty():
        st.caption(body="No bot vs human data for this period.")
        return

    total_bot: int = int(bot_data.filter(bot_data["is_bot"] == True)["events"].sum() or 0)  # noqa: E712
    total_human: int = int(
        bot_data.filter(bot_data["is_bot"] == False)["events"].sum() or 0  # noqa: E712
    )

    if total_bot + total_human == 0:
        st.caption(body="No event data for bot vs human comparison.")
        return

    data: list[dict[str, int | str]] = [
        {"value": int(total_human), "name": "Human"},
        {"value": int(total_bot), "name": "Bot"},
    ]

    colors: list[str] = [PRIMARY, BOT]

    options = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "horizontal", "bottom": 0},
        "series": [
            {
                "name": "Events",
                "type": "pie",
                "radius": ["45%", "70%"],
                "center": ["50%", "50%"],
                "avoidLabelOverlap": True,
                "label": {"fontSize": 13, "fontWeight": "bold"},
                "emphasis": {"label": {"show": True, "fontSize": 15, "fontWeight": "bold"}},
                "data": data,
                "color": colors,
            }
        ],
    }
    st_echarts(options, height="320px")


def _heatmap_pieces(values: list[int], palette: list[str]) -> list[dict[str, Any]]:
    """Build GitHub-style discrete buckets from quartiles of the nonzero values."""
    ordered: list[int] = sorted(values)
    if not ordered:
        return [{"value": 0, "color": palette[0], "label": "No events"}]

    n: int = len(ordered)
    thresholds: list[int] = sorted({ordered[(n * q) // 4] for q in (1, 2, 3)})

    bins: int = len(thresholds) + 1
    step: float = (len(palette) - 2) / (bins - 1) if bins > 1 else 0.0
    colors: list[str] = [palette[1 + round(i * step)] for i in range(bins)]

    pieces: list[dict[str, Any]] = []
    lower: int = 1
    for upper, color in zip(thresholds, colors[:-1], strict=True):
        pieces.append({"min": lower, "max": upper, "color": color, "label": f"{lower:,}–{upper:,}"})
        lower = upper + 1
    pieces.append({"min": lower, "color": colors[-1], "label": f"{lower:,}+"})
    # zeros are explicit empty cells, not the lowest activity bucket
    pieces.insert(0, {"value": 0, "color": palette[0], "label": "No events"})
    return pieces


def render_daily_heatmap(heatmap: DataFrame, color_scheme: str = "blue") -> None:
    """Heatmap: event count by day-of-week x hour, GitHub-style."""
    if heatmap.is_empty():
        st.info(body="No heatmap data for this period.")
        return

    _GREEN = ["#2d2d2d", "#0e4429", "#006d32", "#26a641", "#39d353"]
    _BLUE = ["#2d2d2d", "#1a3a6b", "#1e5ab5", "#3b82f6", "#60a5fa"]

    palette: list[str] = _GREEN if color_scheme == "green" else _BLUE

    dow_labels: list[str] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    hours: list[int] = list(range(24))

    lookup: dict[tuple[Any, Any], Any] = {}
    for row in heatmap.iter_rows(named=True):
        lookup[(row["dow"], row["hour"])] = row["events"]

    data: list[list[int | Any]] = []
    nonzero: list[int] = []
    for d in range(7):
        for h in range(24):
            val: Any = lookup.get((d, h), 0)
            data.append([h, d, val])
            if val > 0:
                nonzero.append(val)

    pieces: list[dict[str, Any]] = _heatmap_pieces(nonzero, palette)

    options = {
        "tooltip": {"position": "top"},
        "grid": {"height": "55%", "top": "10%", "left": "3%", "right": "3%"},
        "xAxis": {
            "type": "category",
            "data": [f"{h:02d}" for h in hours],
            "splitArea": {"show": True},
        },
        "yAxis": {
            "type": "category",
            "data": dow_labels,
            # ECharts renders category index 0 at the bottom by default,
            # which would show the week upside down (Sat → Sun).
            "inverse": True,
            "splitArea": {"show": True},
        },
        "visualMap": {
            "type": "piecewise",
            "pieces": pieces,
            "orient": "horizontal",
            "left": "center",
            "bottom": "10%",
            "itemWidth": 14,
            "itemHeight": 10,
            "textStyle": {"color": "#e0e0e0", "fontSize": 12},
        },
        "series": [
            {
                "name": "Events",
                "type": "heatmap",
                "data": data,
                "label": {"show": False},
                "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0, 0, 0, 0.5)"}},
            }
        ],
    }
    st_echarts(options, height="500px")
