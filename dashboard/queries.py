"""
Dual-mode data reader for the GitPulse dashboard.

DASHBOARD_DATA_SOURCE=minio reads Delta tables from the local MinIO lake (development)
hf (default) downloads the exported Parquet dataset from Hugging Face into the local
Hub cache on first use, then scans it from disk (public dashboard)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

import polars as pl
import streamlit as st
from botocore.exceptions import EndpointConnectionError
from huggingface_hub import hf_hub_download
from polars import DataFrame, LazyFrame

from core.config import settings
from core.helpers.logger import get_logger
from core.helpers.s3 import S3_STORAGE_OPTIONS, get_s3_fs

_logger = get_logger(__name__)

if settings.dashboard.data_source == "minio":
    _logger.info("Using MinIO (delta tables) as data source")
else:
    _logger.info("Using Hugging Face dataset %s as data source", settings.dashboard.hf_dataset)

# MinIO Delta paths (development)
_MINIO_PATHS: dict[str, str] = {
    "gold": f"s3://{settings.minio.bucket_gold}/github/daily_activity",
    "events": f"s3://{settings.minio.bucket_silver}/github/events",
    "actors": f"s3://{settings.minio.bucket_silver}/github/actors",
    "repos": f"s3://{settings.minio.bucket_silver}/github/repos",
    "orgs": f"s3://{settings.minio.bucket_silver}/github/orgs",
}

# Hugging Face Parquet paths (public dashboard) — same layout as the export
_HF_PATHS: dict[str, str] = {
    "gold": "gold/daily_activity.parquet",
    "events": "silver/events.parquet",
    "actors": "silver/actors.parquet",
    "repos": "silver/repos.parquet",
    "orgs": "silver/orgs.parquet",
}


# Internal helpers
def _show_infra_error() -> None:
    """Display a friendly error when the selected data source is unreachable."""
    if settings.dashboard.data_source == "minio":
        body = (
            "## \U0001f4a8 Data Lake not available\n\n"
            "The dashboard cannot load data. This usually means one of the following:\n\n"
            "1. **Infrastructure is not running** \u2014 start MinIO and services:\n\n"
            "   ```bash\n"
            "   make up\n"
            "   ```\n\n"
            "2. **No data in the Gold layer yet** \u2014 run the ETL pipeline:\n\n"
            "   ```bash\n"
            "   make pipeline\n"
            "   ```"
        )
    else:
        body = (
            "## \U0001f4a8 Data source not available\n\n"
            "The dashboard cannot reach the Hugging Face dataset "
            f"`{settings.dashboard.hf_dataset}`. Check your network connection "
            "and the dataset's availability."
        )
    st.error(
        body=body + "\n\nAfter resolving the issue, **refresh this page** to retry.",
        icon=":material/database_off:",
    )
    st.stop()


@st.cache_resource
def _check_minio_connection() -> None:
    """Verify MinIO is reachable. Cached per session and skips the S3 request on subsequent calls."""
    if settings.dashboard.data_source != "minio":
        return
    try:
        get_s3_fs().ls(path=settings.minio.bucket_gold)
    except (EndpointConnectionError, OSError):
        _show_infra_error()


# Internal LazyFrame readers
@st.cache_resource
def _hf_file(rel_path: str) -> str:
    """Download a dataset file into the local Hub cache once and return its path."""
    return hf_hub_download(
        repo_id=settings.dashboard.hf_dataset,
        filename=rel_path,
        repo_type="dataset",
    )


def _lf(table: str) -> LazyFrame:
    """Return a LazyFrame over one dashboard table (MinIO Delta or cached HF Parquet)."""
    if settings.dashboard.data_source == "minio":
        _check_minio_connection()
        return pl.scan_delta(source=_MINIO_PATHS[table], storage_options=S3_STORAGE_OPTIONS)
    return pl.scan_parquet(source=_hf_file(_HF_PATHS[table]))


def _gold_lf() -> LazyFrame:
    """Return a LazyFrame over gold_daily metrics."""
    return _lf(table="gold")


def _actors_lf() -> LazyFrame:
    """Return a LazyFrame over the actors dimension."""
    return _lf(table="actors")


def _repos_lf() -> LazyFrame:
    """Return a LazyFrame over the repos dimension."""
    return _lf(table="repos")


def _orgs_lf() -> LazyFrame:
    """Return a LazyFrame over the orgs dimension."""
    return _lf(table="orgs")


def _silver_events_lf() -> LazyFrame:
    """Return a LazyFrame over silver events."""
    return _lf(table="events")


# Overview page
@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_overview_kpis(
    start: date,
    end: date,
) -> dict[str, Any]:
    """Return the 6 main KPIs for the given period."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )

    kpis: dict[str, Any] = {}

    # KPIs from gold_daily
    row: tuple[Any, ...] = (
        gold.select(
            total_events=pl.col(name="total_events").sum(),
            active_repos=pl.col(name="repo_id").n_unique(),
            avg_pr_merge_rate=pl.col(name="pr_merge_rate").mean(),
            avg_issue_close_rate=pl.col(name="issue_close_rate").mean(),
            avg_gitpulse_score=pl.col(name="gitpulse_score").mean(),
        )
        .collect()
        .row(index=0)
    )
    kpis["total_events"] = row[0]
    kpis["active_repos"] = row[1]
    kpis["avg_pr_merge_rate"] = row[2]
    kpis["avg_issue_close_rate"] = row[3]
    kpis["avg_gitpulse_score"] = row[4]

    # Unique contributors from silver events
    events: LazyFrame = _silver_events_lf().filter(
        pl.col(name="created_at").is_between(
            lower_bound=datetime.combine(date=start, time=datetime.min.time()),
            upper_bound=datetime.combine(date=end, time=datetime.min.time()),
            closed="both",
        )
    )
    kpis["unique_contributors"] = events.select(pl.col(name="actor_id").n_unique()).collect().item()

    return kpis


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_daily_timeline(
    start: date,
    end: date,
) -> DataFrame:
    """Return events per day."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(total_events=pl.col(name="total_events").sum())
        .sort(by="day")
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_event_type_distribution(
    start: date,
    end: date,
) -> dict[str, int]:
    """Return event type distribution."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )

    row: tuple[Any, ...] = (
        lf.select(
            push_events=pl.col(name="push_events").sum(),
            pr_events=pl.col(name="pr_events").sum(),
            issue_events=pl.col(name="issue_events").sum(),
            watch_events=pl.col(name="watch_events").sum(),
            fork_events=pl.col(name="fork_events").sum(),
            release_events=pl.col(name="release_events").sum(),
            comment_events=pl.col(name="comment_events").sum(),
            review_events=pl.col(name="review_events").sum(),
        )
        .collect()
        .row(index=0)
    )
    return {
        "Push": row[0],
        "Pull Request": row[1],
        "Issue": row[2],
        "Watch/Star": row[3],
        "Fork": row[4],
        "Release": row[5],
        "Comment": row[6],
        "Review": row[7],
    }


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_daily_event_breakdown(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily event type counts and average GitPulse score."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(
            push_events=pl.col(name="push_events").sum(),
            pr_events=pl.col(name="pr_events").sum(),
            issue_events=pl.col(name="issue_events").sum(),
            watch_events=pl.col(name="watch_events").sum(),
            fork_events=pl.col(name="fork_events").sum(),
            avg_gitpulse_score=pl.col(name="gitpulse_score").mean(),
        )
        .sort(by="day")
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_top_repos(
    start: date,
    end: date,
    limit: int = 10,
) -> DataFrame:
    """Return top N repos by total events."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    return (
        gold.group_by("repo_id")
        .agg(
            total_events=pl.col(name="total_events").sum(),
            avg_score=pl.col(name="gitpulse_score").mean(),
        )
        .join(other=repos, left_on="repo_id", right_on="id", how="left")
        .sort(by="total_events", descending=True)
        .limit(n=limit)
        .select(
            repo_name=pl.col(name="name"),
            total_events=pl.col(name="total_events").cast(dtype=pl.Int64),
            avg_score=pl.col(name="avg_score").round(decimals=1),
        )
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_trending_repos(
    start: date,
    end: date,
    limit: int = 10,
) -> DataFrame:
    """Return top N repos by stars."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    return (
        gold.group_by("repo_id")
        .agg(
            stars_gained=pl.col(name="watch_events").sum(),
            active_days=pl.col(name="day").n_unique(),
        )
        .filter(pl.col(name="stars_gained") > 0)
        .join(other=repos, left_on="repo_id", right_on="id", how="left")
        .sort(by="stars_gained", descending=True)
        .limit(n=limit)
        .select(
            repo_name=pl.col(name="name"),
            stars_gained=pl.col(name="stars_gained").cast(dtype=pl.Int64),
            active_days=pl.col(name="active_days").cast(dtype=pl.Int64),
        )
        .collect()
    )


# Community page
@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_daily_heatmap(
    end: date,
    event_type: str | None = None,
) -> DataFrame:
    """Return event count by day-of-week x hour (last 7 days only)."""
    heatmap_start: date = end - timedelta(days=7)
    events: LazyFrame = _silver_events_lf().filter(
        pl.col(name="created_at").is_between(
            lower_bound=datetime.combine(date=heatmap_start, time=datetime.min.time()),
            upper_bound=datetime.combine(date=end, time=datetime.min.time()),
            closed="both",
        )
    )
    if event_type:
        events = events.filter(pl.col(name="type") == event_type)
    return (
        events.with_columns(
            dow=(pl.col(name="created_at").dt.weekday() % 7).cast(dtype=pl.Int16),
            hour=pl.col(name="created_at").dt.hour().cast(dtype=pl.Int16),
        )
        .group_by("dow", "hour")
        .agg(events=pl.len().cast(dtype=pl.Int64))
        .sort(by=["dow", "hour"])
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_top_contributors(
    start: date,
    end: date,
    limit: int = 50,
) -> DataFrame:
    """Return top N contributors."""
    events: LazyFrame = _silver_events_lf().filter(
        pl.col(name="created_at").is_between(
            lower_bound=datetime.combine(date=start, time=datetime.min.time()),
            upper_bound=datetime.combine(date=end, time=datetime.min.time()),
            closed="both",
        )
    )
    actors: LazyFrame = _actors_lf()
    return (
        events.join(other=actors, left_on="actor_id", right_on="id", how="left")
        .group_by("login", "is_bot")
        .agg(
            events=pl.len().cast(dtype=pl.Int64),
            repos=pl.col(name="repo_id").n_unique().cast(dtype=pl.Int64),
            prs=pl.col(name="type").eq(other="PullRequestEvent").sum().cast(dtype=pl.Int64),
        )
        .sort(by="events", descending=True)
        .limit(n=limit)
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_contributors_over_time(
    start: date,
    end: date,
) -> DataFrame:
    """Return unique actor count per day."""
    events: LazyFrame = _silver_events_lf().filter(
        pl.col(name="created_at").is_between(
            lower_bound=datetime.combine(date=start, time=datetime.min.time()),
            upper_bound=datetime.combine(date=end, time=datetime.min.time()),
            closed="both",
        )
    )
    actors: LazyFrame = _actors_lf()
    return (
        events.join(other=actors, left_on="actor_id", right_on="id", how="left")
        .with_columns(day=pl.col(name="created_at").dt.date())
        .group_by("day", "is_bot")
        .agg(contributors=pl.col(name="actor_id").n_unique().cast(dtype=pl.Int64))
        .sort(by=["day", "is_bot"])
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_bot_vs_human(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily event count split by is_bot."""
    events: LazyFrame = _silver_events_lf().filter(
        pl.col(name="created_at").is_between(
            lower_bound=datetime.combine(date=start, time=datetime.min.time()),
            upper_bound=datetime.combine(date=end, time=datetime.min.time()),
            closed="both",
        )
    )
    actors: LazyFrame = _actors_lf()
    return (
        events.join(other=actors, left_on="actor_id", right_on="id", how="left")
        .with_columns(day=pl.col(name="created_at").dt.date())
        .group_by("day", "is_bot")
        .agg(events=pl.len().cast(dtype=pl.Int64))
        .sort(by=["day", "is_bot"])
        .collect()
    )


# Development page
@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_pr_metrics(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily PR metrics: opened, merged, merge rate."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(
            prs_opened=pl.col(name="prs_opened").sum(),
            prs_merged=pl.col(name="prs_merged").sum(),
            prs_closed_unmerged=pl.col(name="prs_closed_unmerged").sum(),
            avg_merge_rate=pl.col(name="pr_merge_rate").mean(),
        )
        .sort(by="day")
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_pr_bot_breakdown(
    start: date,
    end: date,
) -> DataFrame:
    """Return PR event count split by bot vs human."""
    events: LazyFrame = _silver_events_lf().filter(
        pl.col(name="created_at").is_between(
            lower_bound=datetime.combine(date=start, time=datetime.min.time()),
            upper_bound=datetime.combine(date=end, time=datetime.min.time()),
            closed="both",
        ),
        pl.col(name="type") == "PullRequestEvent",
    )
    actors: LazyFrame = _actors_lf()
    return (
        events.join(other=actors, left_on="actor_id", right_on="id", how="left")
        .with_columns(day=pl.col(name="created_at").dt.date())
        .group_by("day", "is_bot")
        .agg(prs=pl.len().cast(dtype=pl.Int64))
        .sort(by=["day", "is_bot"])
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_issue_metrics(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily issue metrics: opened, closed, close rate."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(
            issues_opened=pl.col(name="issues_opened").sum(),
            issues_closed=pl.col(name="issues_closed").sum(),
            avg_close_rate=pl.col(name="issue_close_rate").mean(),
        )
        .sort(by="day")
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_code_review_metrics(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily review and comment activity relative to PRs."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(
            pr_events=pl.col(name="pr_events").sum(),
            review_events=pl.col(name="review_events").sum(),
            comment_events=pl.col(name="comment_events").sum(),
        )
        .sort(by="day")
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_repo_health(
    start: date,
    end: date,
    limit: int = 10,
) -> DataFrame:
    """Return top repos with health indicators."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    return (
        gold.group_by("repo_id")
        .agg(
            total_events=pl.col(name="total_events").sum(),
            avg_score=pl.col(name="gitpulse_score").mean(),
            avg_merge_rate=pl.col(name="pr_merge_rate").mean(),
            avg_close_rate=pl.col(name="issue_close_rate").mean(),
            total_reviews=pl.col(name="review_events").sum(),
            total_prs=pl.col(name="pr_events").sum(),
        )
        .join(other=repos, left_on="repo_id", right_on="id", how="left")
        .sort(by="total_events", descending=True)
        .limit(n=limit)
        .select(
            repo_name=pl.col(name="name"),
            total_events=pl.col(name="total_events").cast(dtype=pl.Int64),
            avg_score=pl.col(name="avg_score").round(decimals=1),
            avg_merge_rate=pl.col(name="avg_merge_rate").round(decimals=3),
            avg_close_rate=pl.col(name="avg_close_rate").round(decimals=3),
            review_per_pr=pl.when(pl.col(name="total_prs") > 0)
            .then(
                statement=(pl.col(name="total_reviews") / pl.col(name="total_prs")).round(
                    decimals=2
                )
            )
            .otherwise(statement=pl.lit(value=None)),
        )
        .collect()
    )


# Ecosystem page
@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_ecosystem_health_kpis(
    start: date,
    end: date,
) -> dict[str, float | int | None]:
    """Return ecosystem health indicators."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )

    daily: DataFrame = (
        gold.group_by("day")
        .agg(
            active_repos=pl.col(name="repo_id").n_unique(),
            stars=pl.col(name="watch_events").sum(),
            forks=pl.col(name="fork_events").sum(),
        )
        .collect()
    )

    totals: tuple[Any, ...] = (
        gold.select(
            active_repos=pl.col(name="repo_id").n_unique(),
            total_stars=pl.col(name="watch_events").sum(),
            total_forks=pl.col(name="fork_events").sum(),
            avg_gitpulse_score=pl.col(name="gitpulse_score").mean(),
            unique_actors=pl.col(name="unique_actors").sum(),
        )
        .collect()
        .row(index=0)
    )

    avg_active: Any | Literal[0] = (
        daily.select(pl.col(name="active_repos").mean()).item() if not daily.is_empty() else 0
    )
    avg_stars: Any | Literal[0] = (
        daily.select(pl.col(name="stars").mean()).item() if not daily.is_empty() else 0
    )
    star_fork_ratio: int | None = (
        round(number=totals[1] / totals[2], ndigits=1) if totals[2] > 0 else None
    )

    return {
        "active_repos": int(totals[0]),
        "total_stars": int(totals[1]),
        "total_forks": int(totals[2]),
        "avg_gitpulse_score": round(number=float(totals[3]), ndigits=1),
        "unique_actors": int(totals[4]),
        "avg_stars_per_day": round(number=float(avg_stars), ndigits=1),
        "avg_active_repos_per_day": round(number=float(avg_active), ndigits=1),
        "star_fork_ratio": star_fork_ratio,
    }


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_org_summary(
    start: date,
    end: date,
) -> DataFrame:
    """Return aggregated metrics per organization."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    orgs: LazyFrame = _orgs_lf()
    return (
        gold.filter(pl.col(name="org_id").is_not_null())
        .group_by("org_id")
        .agg(
            total_events=pl.col(name="total_events").sum(),
            active_repos=pl.col(name="repo_id").n_unique(),
            avg_gitpulse_score=pl.col(name="gitpulse_score").mean(),
            push_events=pl.col(name="push_events").sum(),
            pr_events=pl.col(name="pr_events").sum(),
            issue_events=pl.col(name="issue_events").sum(),
            watch_events=pl.col(name="watch_events").sum(),
        )
        .join(other=orgs, left_on="org_id", right_on="id", how="left")
        .sort(by="total_events", descending=True)
        .select(
            org_name=pl.col(name="login"),
            total_events=pl.col(name="total_events").cast(dtype=pl.Int64),
            active_repos=pl.col(name="active_repos").cast(dtype=pl.Int64),
            avg_gitpulse_score=pl.col(name="avg_gitpulse_score").round(decimals=1),
        )
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_active_repos_over_time(
    start: date,
    end: date,
) -> DataFrame:
    """Return unique active repos per day."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(active_repos=pl.col(name="repo_id").n_unique())
        .sort(by="day")
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_star_growth(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily star (WatchEvent) counts."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(stars=pl.col(name="watch_events").sum())
        .sort(by="day")
        .with_columns(cumulative_stars=pl.col(name="stars").cum_sum().cast(dtype=pl.Int64))
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_fork_growth(
    start: date,
    end: date,
) -> DataFrame:
    """Return daily fork counts."""
    lf: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    return (
        lf.group_by("day")
        .agg(forks=pl.col(name="fork_events").sum())
        .sort(by="day")
        .with_columns(cumulative_forks=pl.col(name="forks").cum_sum().cast(dtype=pl.Int64))
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_top_forked_repos(
    start: date,
    end: date,
    limit: int = 10,
) -> DataFrame:
    """Return top N repos by fork events."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    return (
        gold.group_by("repo_id")
        .agg(fork_events=pl.col(name="fork_events").sum())
        .filter(pl.col(name="fork_events") > 0)
        .join(other=repos, left_on="repo_id", right_on="id", how="left")
        .sort(by="fork_events", descending=True)
        .limit(n=limit)
        .select(
            repo_name=pl.col(name="name"),
            forks=pl.col(name="fork_events").cast(dtype=pl.Int64),
        )
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_top_open_repos(
    start: date,
    end: date,
    limit: int = 10,
    sort_by: Literal["issues", "prs"] = "issues",
) -> DataFrame:
    """Return top N repos by issues or PRs opened."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    sort_col: Literal["prs_opened", "issues_opened"] = (
        "prs_opened" if sort_by == "prs" else "issues_opened"
    )
    return (
        gold.group_by("repo_id")
        .agg(
            issues_opened=pl.col(name="issues_opened").sum(),
            prs_opened=pl.col(name="prs_opened").sum(),
        )
        .join(repos, left_on="repo_id", right_on="id", how="left")
        .sort(sort_col, descending=True)
        .limit(limit)
        .select(
            repo_name=pl.col(name="name"),
            issues_opened=pl.col(name="issues_opened").cast(dtype=pl.Int64),
            prs_opened=pl.col(name="prs_opened").cast(dtype=pl.Int64),
        )
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_stars_vs_forks(
    start: date,
    end: date,
    limit: int = 60,
) -> DataFrame:
    """Return per-repo star and fork counts."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    orgs: LazyFrame = _orgs_lf()
    return (
        gold.group_by("repo_id")
        .agg(
            stars_gained=pl.col(name="watch_events").sum(),
            forks=pl.col(name="fork_events").sum(),
            org_id=pl.col(name="org_id").first(),
        )
        .filter((pl.col(name="stars_gained") > 0) | (pl.col(name="forks") > 0))
        .join(other=repos.select("id", "name"), left_on="repo_id", right_on="id", how="left")
        .join(other=orgs.select("id", "login"), left_on="org_id", right_on="id", how="left")
        .sort(by="stars_gained", descending=True)
        .limit(n=limit)
        .select(
            repo_name=pl.col(name="name"),
            stars_gained=pl.col(name="stars_gained").cast(dtype=pl.Int64),
            forks=pl.col(name="forks").cast(dtype=pl.Int64),
            org_name=pl.col(name="login"),
        )
        .collect()
    )


@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_star_engagement_conversion(
    start: date,
    end: date,
    limit: int = 20,
) -> DataFrame:
    """Return repos with star counts and engagement totals."""
    gold: LazyFrame = _gold_lf().filter(
        pl.col(name="day").is_between(lower_bound=start, upper_bound=end, closed="both")
    )
    repos: LazyFrame = _repos_lf()
    orgs: LazyFrame = _orgs_lf()
    return (
        gold.group_by("repo_id")
        .agg(
            stars=pl.col(name="watch_events").sum(),
            engagement=pl.col(name="pr_events").sum() + pl.col(name="issue_events").sum(),
            org_id=pl.col(name="org_id").first(),
        )
        .filter(pl.col(name="stars") > 0)
        .join(other=repos.select("id", "name"), left_on="repo_id", right_on="id", how="left")
        .join(other=orgs.select("id", "login"), left_on="org_id", right_on="id", how="left")
        .with_columns(
            conversion_rate=pl.when(pl.col(name="stars") > 0)
            .then(statement=(pl.col(name="engagement") / pl.col(name="stars")).round(decimals=3))
            .otherwise(statement=pl.lit(value=None)),
        )
        .sort(by="stars", descending=True)
        .limit(n=limit)
        .select(
            repo_name=pl.col(name="name"),
            stars=pl.col(name="stars").cast(dtype=pl.Int64),
            engagement=pl.col(name="engagement").cast(dtype=pl.Int64),
            conversion_rate=pl.col(name="conversion_rate"),
            org_name=pl.col(name="login"),
        )
        .collect()
    )


# Shared helpers
@st.cache_data(ttl=settings.dashboard.cache_ttl, show_spinner=False)
def get_date_range() -> tuple[date, date] | None:
    """Return the min and max day available in gold_daily."""
    try:
        row: tuple[Any, ...] = (
            _gold_lf()
            .select(min_day=pl.col(name="day").min(), max_day=pl.col(name="day").max())
            .collect()
            .row(index=0)
        )
        return row[0], row[1]
    except (EndpointConnectionError, OSError, FileNotFoundError):
        _show_infra_error()
