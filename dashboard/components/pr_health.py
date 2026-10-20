"""
Code & PR Health: PR metrics, merge rates, funnel, and bot comparison.

Uses streamlit_echarts for dual line, funnel, and grouped bar charts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pandas.core.frame
import streamlit as st
from polars import DataFrame
from streamlit_echarts import st_echarts

from dashboard.components._palette import (
    BOT,
    DANGER,
    HUMAN,
    INFO,
    MERGED,
    OPENED,
    PRIMARY,
    SUCCESS,
    WARNING,
)


def render_pr_opened_vs_merged(pr_metrics: DataFrame) -> None:
    """Dual line chart: PRs opened vs merged per day."""
    if pr_metrics.is_empty():
        st.info(body="No PR data for the current selection.")
        return

    days: list[Any] = pr_metrics["day"].dt.strftime(format="%Y-%m-%d").to_list()
    opened: list[Any] = pr_metrics["prs_opened"].to_list()
    merged: list[Any] = pr_metrics["prs_merged"].to_list()

    options = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["Opened", "Merged"], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "boundaryGap": False,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {"type": "value", "minInterval": 1},
        "series": [
            {
                "name": "Opened",
                "type": "line",
                "data": opened,
                "smooth": True,
                "lineStyle": {"width": 2},
                "itemStyle": {"color": OPENED},
            },
            {
                "name": "Merged",
                "type": "line",
                "data": merged,
                "smooth": True,
                "lineStyle": {"width": 2},
                "itemStyle": {"color": MERGED},
            },
        ],
    }
    st_echarts(options, height="360px")


def render_pr_merge_rate(pr_metrics: DataFrame, overall_mean: float | None = None) -> None:
    """Line chart: PR merge rate over time with period-average markLine."""
    if pr_metrics.is_empty():
        st.info(body="No PR data for the current selection.")
        return

    days: list[Any] = pr_metrics["day"].dt.strftime(format="%Y-%m-%d").to_list()
    rates_pct = [
        round(number=r * 100, ndigits=1) if r is not None else None
        for r in pr_metrics["avg_merge_rate"].to_list()
    ]

    legend: list[str] = ["Merge rate"]
    series = [
        {
            "name": "Merge rate",
            "type": "line",
            "data": rates_pct,
            "smooth": True,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": INFO},
            "areaStyle": {"color": "rgba(6, 182, 212, 0.15)"},
        },
    ]

    if overall_mean is not None:
        mean_pct: int | float = round(number=overall_mean * 100, ndigits=1)
        legend.append("Period avg")
        series.append(
            {
                "name": "Period avg",
                "type": "line",
                "data": [],
                "lineStyle": {"width": 0},
                "symbol": "none",
                "markLine": {
                    "silent": True,
                    "data": [
                        {
                            "yAxis": mean_pct,
                        }
                    ],
                    "symbol": "none",
                },
            }
        )

    options = {
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>Merge rate: {c}%"},
        "legend": {"data": legend, "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "boundaryGap": False,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {
            "type": "value",
            "min": 0,
            "max": 100,
            "axisLabel": {"formatter": "{value}%"},
        },
        "series": series,
    }
    st_echarts(options, height="360px")


def render_pr_funnel(pr_metrics: DataFrame) -> None:
    """Nightingale rose chart: PR funnel from opened → merged."""
    if pr_metrics.is_empty():
        st.info(body="No PR data for the current selection.")
        return

    total_opened = int(pr_metrics["prs_opened"].sum())
    total_merged = int(pr_metrics["prs_merged"].sum())
    total_closed_unmerged = int(pr_metrics["prs_closed_unmerged"].sum())
    total_open_remaining = max(total_opened - total_merged - total_closed_unmerged, 0)

    data: list[dict[str, int | str]] = [
        {"value": total_opened, "name": "Opened"},
        {"value": total_merged, "name": "Merged"},
        {"value": total_closed_unmerged, "name": "Closed w/o merge"},
        {"value": total_open_remaining, "name": "Still open"},
    ]

    options = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"bottom": 0},
        "series": [
            {
                "name": "PR Funnel",
                "type": "pie",
                "roseType": "area",
                "radius": ["20%", "80%"],
                "center": ["50%", "50%"],
                "avoidLabelOverlap": True,
                "itemStyle": {"borderRadius": 4},
                "label": {
                    "show": True,
                    "fontSize": 12,
                    "formatter": "{b}\n{c}",
                },
                "emphasis": {
                    "label": {"fontSize": 14, "fontWeight": "bold"},
                },
                "data": data,
                "color": [PRIMARY, SUCCESS, DANGER, WARNING],
            }
        ],
    }
    st_echarts(options, height="363px")


def render_pr_bot_comparison(pr_bot_data: DataFrame) -> None:
    """Grouped bar chart: PRs by bot vs human per day."""
    if pr_bot_data.is_empty():
        st.info(body="No PR bot breakdown data for this period.")
        return

    # Use pandas pivot to reshape (day × is_bot) safely
    pdf = pr_bot_data.to_pandas()
    pivoted = pdf.pivot_table(
        index="day", columns="is_bot", values="prs", aggfunc="sum", fill_value=0
    ).sort_index()

    days = [d.strftime("%Y-%m-%d") for d in pivoted.index]
    human_prs: list[int] = [
        int(v) for v in pivoted.get(key=False, default=pd.Series(data=[0] * len(pivoted))).tolist()
    ]
    bot_prs: list[int] = [
        int(v) for v in pivoted.get(key=True, default=pd.Series(data=[0] * len(pivoted))).tolist()
    ]

    series = [
        {
            "name": "Human",
            "type": "bar",
            "data": human_prs,
            "itemStyle": {"color": HUMAN},
        },
        {
            "name": "Bot",
            "type": "bar",
            "data": bot_prs,
            "itemStyle": {"color": BOT},
        },
    ]

    options = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": [s["name"] for s in series], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {"type": "value", "minInterval": 1},
        "series": series,
    }
    st_echarts(options, height="360px")
