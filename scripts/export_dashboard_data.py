"""
Export static Parquet files for the public Streamlit dashboard.

Usage:
    uv run python scripts/export_dashboard_data.py                # last 7 days (default)
    uv run python scripts/export_dashboard_data.py --days 15      # last 15 days

Options:
    --days N                       # days of lookback before the last complete day (default: 7)
"""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
from polars.dataframe.frame import DataFrame

from core.config import settings
from core.helpers.logger import cyan, get_logger, green, magenta
from core.helpers.s3 import S3_STORAGE_OPTIONS

DEFAULT_DAYS: int = 7

OUTPUT_DIR = Path(settings.dashboard.export_path)

_MINIO_SILVER = {
    "orgs": f"s3://{settings.minio.bucket_silver}/github/orgs",
    "repos": f"s3://{settings.minio.bucket_silver}/github/repos",
    "actors": f"s3://{settings.minio.bucket_silver}/github/actors",
    "events": f"s3://{settings.minio.bucket_silver}/github/events",
}

_MINIO_GOLD = f"s3://{settings.minio.bucket_gold}/github/daily_activity"

# only columns the dashboard actually needs
_DIM_COLS = {
    "orgs": ["id", "login"],
    "repos": ["id", "name"],
    "actors": ["id", "login", "is_bot"],
}


def export_dashboard_data(days: int = DEFAULT_DAYS) -> None:
    """
    Export static Parquet files for the Streamlit dashboard.

    Args:
        days: Days of lookback before the last complete day. The window is
            inclusive, so N yields N+1 calendar days, clamped to the days
            actually present in gold.
    """
    logger = get_logger(__name__)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # the current UTC day is still in progress, so it never enters the window
    last_complete_day: date = datetime.now(UTC).date() - timedelta(days=1)

    window: DataFrame = (
        pl.scan_delta(source=_MINIO_GOLD, storage_options=S3_STORAGE_OPTIONS)
        .select(
            pl.col(name="day").min().alias("first_day"),
            pl.col(name="day")
            .filter(pl.col(name="day") <= last_complete_day)
            .max()
            .alias("last_day"),
        )
        .collect()
    )
    first_day: date | None = window.item(row=0, column="first_day")
    max_day: date | None = window.item(row=0, column="last_day")

    if max_day is None or first_day is None:
        msg = f"no complete day in gold (latest elapsed UTC day: {last_complete_day}) — run `make pipeline` first"
        raise RuntimeError(msg)

    min_day: date = max(first_day, max_day - timedelta(days=days))

    logger.info(
        "range: %s → %s  (%d days)",
        cyan(text=str(object=min_day)),
        cyan(text=str(object=max_day)),
        (max_day - min_day).days + 1,
    )

    # export gold metrics
    gold_daily_activity_path: Path = OUTPUT_DIR / "gold" / "daily_activity.parquet"
    _reset_path(path=gold_daily_activity_path)

    (
        pl.scan_delta(source=_MINIO_GOLD, storage_options=S3_STORAGE_OPTIONS)
        .filter(
            pl.col(name="day").is_between(
                lower_bound=min_day,
                upper_bound=max_day,
                closed="both",
            )
        )
        .sink_parquet(
            path=str(object=gold_daily_activity_path),
            compression="zstd",
            mkdir=True,
        )
    )
    _log_size(path=gold_daily_activity_path, label="gold/daily_activity", logger=logger)

    # get start and end datetime for filtering silver events
    start_dt: datetime = datetime.combine(date=min_day, time=datetime.min.time())
    end_dt: datetime = datetime.combine(date=max_day + timedelta(days=1), time=datetime.min.time())

    # export silver events as a single file
    silver_events_path: Path = OUTPUT_DIR / "silver" / "events.parquet"
    _reset_path(path=silver_events_path)

    (
        pl.scan_delta(source=_MINIO_SILVER["events"], storage_options=S3_STORAGE_OPTIONS)
        .filter(
            pl.col(name="created_at").is_between(
                lower_bound=start_dt, upper_bound=end_dt, closed="left"
            )
        )
        .drop("year", "month", "day", "hour")
        .sink_parquet(
            path=str(object=silver_events_path),
            compression="zstd",
            mkdir=True,
        )
    )
    _log_size(path=silver_events_path, label="silver/events", logger=logger)

    # export silver actors, repos and orgs dimensions (deduplicated)
    for dim_name in ("actors", "repos", "orgs"):
        output_path: Path = OUTPUT_DIR / "silver" / f"{dim_name}.parquet"
        _reset_path(path=output_path)

        pl.scan_delta(
            source=_MINIO_SILVER[dim_name],
            storage_options=S3_STORAGE_OPTIONS,
        ).sort(
            "id",
            "first_seen_at",
            descending=[False, True],
        ).unique(subset=["id"], keep="first").select(
            _DIM_COLS[dim_name],
        ).sink_parquet(
            path=str(object=output_path),
            compression="zstd",
        )
        _log_size(path=output_path, label=f"silver/{dim_name}", logger=logger)

    logger.info(
        "✓ export complete — %s",
        green(text=str(object=OUTPUT_DIR)),
    )


def _reset_path(path: Path) -> None:
    """Remove a previous export at `path` (file or directory) so the write starts clean."""
    if path.is_dir():
        shutil.rmtree(path=path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _log_size(path: Path, label: str, logger) -> None:
    """Log the size of an exported Parquet file."""
    size_mb: float = path.stat().st_size / (1024 * 1024)
    logger.info("%s — %s", green(text=label), magenta(text=f"{size_mb:.1f} MB"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export static Parquet files for the public Streamlit dashboard."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"days of lookback before the last complete day (default: {DEFAULT_DAYS})",
    )
    args = parser.parse_args()

    export_dashboard_data(days=args.days)
