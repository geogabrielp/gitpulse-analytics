"""
Ecosystem & Growth: star growth, fork activity, trending repos, org summaries, and star-to-engagement conversion.

Uses streamlit_echarts for bar, line, grouped bar, and scatter charts.
"""

from __future__ import annotations

from typing import Any, Literal

import streamlit as st
from polars import DataFrame
from streamlit_echarts import JsCode, st_echarts

from dashboard.components._palette import (
    DANGER,
    INFO,
    PRIMARY,
    SUCCESS,
    VIOLET,
    WARNING,
)


def render_star_growth(star_data: DataFrame, mode: str = "stars") -> None:
    """Dual-axis chart: daily (bar) + cumulative (line)."""
    if star_data.is_empty():
        st.info(body=f"No {mode} activity for the current selection.")
        return

    daily_col: Literal["stars", "forks"] = "stars" if mode == "stars" else "forks"
    cumul_col: Literal["cumulative_stars", "cumulative_forks"] = (
        "cumulative_stars" if mode == "stars" else "cumulative_forks"
    )
    bar_label: Literal["Daily stars", "Daily forks"] = (
        "Daily stars" if mode == "stars" else "Daily forks"
    )
    line_label: Literal["Cumulative stars", "Cumulative forks"] = (
        "Cumulative stars" if mode == "stars" else "Cumulative forks"
    )

    bar_color = WARNING if mode == "stars" else INFO
    line_color = DANGER if mode == "stars" else PRIMARY

    days: list[Any] = star_data["day"].dt.strftime(format="%Y-%m-%d").to_list()
    daily: list[Any] = star_data[daily_col].to_list()
    cumulative: list[Any] = star_data[cumul_col].to_list()

    options = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [bar_label, line_label], "bottom": 0},
        "grid": {
            "left": "3%",
            "right": "4%",
            "bottom": "15%",
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "data": days,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": [
            {
                "type": "value",
                "name": bar_label,
                "minInterval": 1,
            },
            {
                "type": "value",
                "name": "Cumulative",
                "minInterval": 1,
            },
        ],
        "series": [
            {
                "name": bar_label,
                "type": "bar",
                "data": daily,
                "itemStyle": {"color": bar_color, "borderRadius": [4, 4, 0, 0]},
            },
            {
                "name": line_label,
                "type": "line",
                "yAxisIndex": 1,
                "data": cumulative,
                "smooth": True,
                "lineStyle": {"width": 2},
                "itemStyle": {"color": line_color},
                "areaStyle": {"opacity": 0.1},
                "symbol": "none",
            },
        ],
    }
    st_echarts(options, height="360px")


def render_top_forks(forks: DataFrame) -> None:
    """Horizontal bar chart: top N repos by fork events."""
    if forks.is_empty():
        st.info(body="No fork data for the current selection.")
        return

    names: list[Any] = forks["repo_name"].to_list()[::-1]
    values: list[Any] = forks["forks"].to_list()[::-1]

    options = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": "3%", "right": "8%", "bottom": "3%", "containLabel": True},
        "xAxis": {"type": "value", "minInterval": 1},
        "yAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"fontSize": 11},
        },
        "series": [
            {
                "name": "Forks",
                "type": "bar",
                "data": values,
                "itemStyle": {"color": INFO, "borderRadius": [0, 4, 4, 0]},
            }
        ],
    }
    st_echarts(options, height="320px")


def render_daily_forks(daily_forks: DataFrame) -> None:
    """Line chart: fork events per day."""
    if daily_forks.is_empty():
        st.info(body="No fork activity for the current selection.")
        return

    days: list[Any] = daily_forks["day"].dt.strftime("%Y-%m-%d").to_list()
    values: list[Any] = daily_forks["forks"].to_list()

    options = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "boundaryGap": False,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {"type": "value", "minInterval": 1},
        "series": [
            {
                "name": "Forks",
                "type": "line",
                "data": values,
                "smooth": True,
                "lineStyle": {"width": 2},
                "areaStyle": {"opacity": 0.15},
                "itemStyle": {"color": INFO},
            }
        ],
    }
    st_echarts(options, height="360px")


def render_top_open_repos(
    open_data: DataFrame,
    show: str = "both",
) -> None:
    """Horizontal bar chart: top N repos by issues and/or PRs opened."""
    if open_data.is_empty():
        st.info(body="No issue/PR data for the current selection.")
        return

    names: list[Any] = open_data["repo_name"].to_list()[::-1]
    values: list[Any] = open_data["issues_opened" if show == "issues" else "prs_opened"].to_list()[
        ::-1
    ]
    color = WARNING if show == "issues" else PRIMARY

    options = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {
            "left": "3%",
            "right": "4%",
            "bottom": "3%",
            "containLabel": True,
        },
        "xAxis": {"type": "value", "minInterval": 1},
        "yAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"fontSize": 11},
        },
        "series": [
            {
                "name": "Open issues" if show == "issues" else "Open PRs",
                "type": "bar",
                "data": values,
                "itemStyle": {"color": color, "borderRadius": [0, 4, 4, 0]},
            }
        ],
    }
    st_echarts(options, height="320px")


def render_trending_repos(trending: DataFrame, mode: str = "stars") -> None:
    """Horizontal bar chart: top N repos by stars or forks gained."""
    if trending.is_empty():
        st.info(body=f"No trending {mode} data for the current selection.")
        return

    val_col = "stars_gained" if mode == "stars" else "forks"
    bar_color = DANGER if mode == "stars" else INFO

    names: list[Any] = trending["repo_name"].to_list()[::-1]
    values: list[Any] = trending[val_col].to_list()[::-1]

    options = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": "3%", "right": "8%", "bottom": "3%", "containLabel": True},
        "xAxis": {"type": "value", "minInterval": 1},
        "yAxis": {
            "type": "category",
            "data": names,
            "axisLabel": {"fontSize": 11},
        },
        "series": [
            {
                "name": "Stars gained" if mode == "stars" else "Forks",
                "type": "bar",
                "data": values,
                "itemStyle": {"color": bar_color, "borderRadius": [0, 4, 4, 0]},
            }
        ],
    }
    st_echarts(options, height="320px")


def render_stars_vs_forks_scatter(data: DataFrame) -> None:
    """
    Scatter chart: stars gained vs forks per repo.

    Each dot is a repository. Hover reveals repo name and organisation.
    """
    if data.is_empty():
        st.info(body="Insufficient data for the stars vs forks scatter.")
        return

    scatter_data: list[dict[str, list[Any | str] | Any]] = [
        {
            "value": [r["stars_gained"], r["forks"], r["repo_name"], r["org_name"] or "n/a"],
            "name": r["repo_name"],
        }
        for r in data.to_dicts()
    ]

    options = {
        "title": {
            "text": "Popularity x Utility",
            "left": "center",
            "textStyle": {"fontSize": 14},
        },
        "tooltip": {
            "trigger": "item",
            "formatter": JsCode(
                js_code="""
                function(params) {
                    var v = params.data.value;
                    return '<b>' + v[2] + '</b><br/>' +
                        '<span style=\"display:inline-block;margin-right:4px;' +
                        'border-radius:10px;width:10px;height:10px;' +
                        'background-color:#8B5CF6;\"></span> Stars gained: ' + v[0] + '<br/>' +
                        '<span style=\"display:inline-block;margin-right:4px;' +
                        'border-radius:10px;width:10px;height:10px;' +
                        'background-color:#06B6D4;\"></span> Forks: ' + v[1] + '<br/>' +
                        '<span style=\"display:inline-block;margin-right:4px;' +
                        'border-radius:10px;width:10px;height:10px;' +
                        'background-color:#8B5CF6;\"></span> Org: ' + v[3];
                }
                """
            ),
        },
        "grid": {"left": "5%", "right": "5%", "bottom": "8%", "containLabel": True},
        "xAxis": {
            "name": "Stars gained",
            "nameLocation": "middle",
            "nameGap": 30,
            "nameTextStyle": {"fontSize": 12},
            "minInterval": 1,
            "axisLabel": {"fontSize": 11},
            "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.9}},
        },
        "yAxis": {
            "name": "Forks",
            "nameLocation": "middle",
            "nameGap": 45,
            "nameTextStyle": {"fontSize": 12},
            "minInterval": 1,
            "axisLabel": {"fontSize": 11},
            "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.9}},
        },
        "series": [
            {
                "type": "scatter",
                "symbolSize": 12,
                "data": scatter_data,
                "itemStyle": {
                    "color": INFO,
                    "opacity": 0.4,
                    "borderColor": "#7C3AED",
                    "borderWidth": 1,
                },
                "label": {"show": False},
            }
        ],
    }
    st_echarts(options, height="400px")


def render_active_repos_over_time(repo_data: DataFrame) -> None:
    """Line chart: unique active repositories per day."""
    if repo_data.is_empty():
        st.info(body="No activity data for the current selection.")
        return

    days: list[Any] = repo_data["day"].dt.strftime(format="%Y-%m-%d").to_list()
    values: list[Any] = repo_data["active_repos"].to_list()

    options = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": days,
            "boundaryGap": False,
            "axisLabel": {"rotate": 45, "fontSize": 10},
        },
        "yAxis": {"type": "value", "minInterval": 1},
        "series": [
            {
                "name": "Active repos",
                "type": "line",
                "data": values,
                "smooth": True,
                "lineStyle": {"width": 2},
                "areaStyle": {"opacity": 0.15},
                "itemStyle": {"color": SUCCESS},
            }
        ],
    }
    st_echarts(options, height="360px")


def render_star_engagement_conversion(conversion_data: DataFrame) -> None:
    """
    Scatter chart: stars vs engagement (PRs + Issues), uniform style.

    Each dot is a repository. Mirrors the Stars vs Forks scatter style.
    """
    if conversion_data.is_empty():
        st.info(body="No star or engagement data for the current selection.")
        return

    scatter_data: list[dict[str, list[Any | str] | Any]] = [
        {
            "value": [r["stars"], r["engagement"], r["repo_name"], r["org_name"] or "n/a"],
            "name": r["repo_name"],
        }
        for r in conversion_data.to_dicts()
    ]

    options = {
        "title": {
            "text": "Popularity x Contribution",
            "left": "center",
            "textStyle": {"fontSize": 14},
        },
        "tooltip": {
            "trigger": "item",
            "formatter": JsCode(
                js_code="""
                function(params) {
                    var v = params.data.value;
                    return '<b>' + v[2] + '</b><br/>' +
                        '<span style=\"display:inline-block;margin-right:4px;' +
                        'border-radius:10px;width:10px;height:10px;' +
                        'background-color:#8B5CF6;\"></span> Stars: ' + v[0] + '<br/>' +
                        '<span style=\"display:inline-block;margin-right:4px;' +
                        'border-radius:10px;width:10px;height:10px;' +
                        'background-color:#3B82F6;\"></span> Engagement: ' + v[1] + '<br/>' +
                        '<span style=\"display:inline-block;margin-right:4px;' +
                        'border-radius:10px;width:10px;height:10px;' +
                        'background-color:#8B5CF6;\"></span> Org: ' + v[3];
                }
                """
            ),
        },
        "grid": {"left": "5%", "right": "5%", "bottom": "8%", "containLabel": True},
        "xAxis": {
            "name": "Stars gained",
            "nameLocation": "middle",
            "nameGap": 30,
            "nameTextStyle": {"fontSize": 12},
            "minInterval": 1,
            "axisLabel": {"fontSize": 11},
            "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.9}},
        },
        "yAxis": {
            "name": "Engagement (PRs + Issues)",
            "nameLocation": "middle",
            "nameGap": 45,
            "nameTextStyle": {"fontSize": 12},
            "minInterval": 1,
            "axisLabel": {"fontSize": 11},
            "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.9}},
        },
        "series": [
            {
                "type": "scatter",
                "symbolSize": 12,
                "data": scatter_data,
                "itemStyle": {
                    "color": VIOLET,
                    "opacity": 0.4,
                    "borderColor": "#7C3AED",
                    "borderWidth": 1,
                },
                "label": {"show": False},
            }
        ],
    }
    st_echarts(options, height="400px")


def render_ecosystem_kpis(kpis: dict[str, float | int | None]) -> None:
    """Render 4 ecosystem health KPI cards at the top of the page."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        ratio: int | float | None = kpis.get("star_fork_ratio")
        st.metric(
            label=":material/compare_arrows: Star-to-Fork ratio",
            value=f"{ratio}:1" if ratio is not None else "N/A",
            help="(Stars per fork) high = discovery ecosystem, low = utility ecosystem.",
            border=True,
        )
    with col2:
        st.metric(
            label=":material/star: Total stars",
            value=f"{int(kpis.get('total_stars') or 0):,}",
            help="Total WatchEvent (star) activity in the period.",
            border=True,
        )
    with col3:
        st.metric(
            label=":material/speed: Star velocity / day",
            value=f"{int(kpis.get('avg_stars_per_day') or 0):,}",
            help="Average stars gained per day in the period.",
            border=True,
        )
    with col4:
        st.metric(
            label=":material/dynamic_feed: Daily active repos / day",
            value=f"{int(kpis.get('avg_active_repos_per_day') or 0):,}",
            help="Average unique repositories with activity per day (ecosystem pulse).",
            border=True,
        )
