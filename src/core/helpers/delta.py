"""
Delta Lake helpers: append-only facts, day-level replaces, SCD Type 1 dimensions.
"""

from __future__ import annotations

import polars as pl
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import TableNotFoundError
from polars import DataFrame, LazyFrame

from core.helpers.logger import cyan, get_logger, magenta
from core.helpers.s3 import S3_STORAGE_OPTIONS


def append_delta(
    df: DataFrame,
    target: str,
    partition_by: list[str] | None = None,
) -> None:
    """
    Append *df* to a Delta table, creating it if it doesn't exist.

    Designed for immutable fact tables (e.g. GitHub events). Uses
    `write_deltalake(mode="append")` no merge, no predicate.
    """
    logger = get_logger(__name__)

    write_deltalake(
        target,
        df.to_arrow(),
        storage_options=S3_STORAGE_OPTIONS,
        mode="append",
        partition_by=partition_by or [],
    )

    logger.info("appended %s rows into %s", magenta(len(df)), cyan(target))


def replace_days_delta(
    df: DataFrame,
    target: str,
    days_col: str = "day",
    partition_by: list[str] | None = None,
) -> None:
    """
    Atomically replace the `days_col` days present in *df*.

    One commit (mode="overwrite" + predicate), so there is no window where
    the days are missing.

    Built for the Gold aggregate, whose newest day is still growing.
    """
    logger = get_logger(__name__)

    days: list[str] = sorted({day.isoformat() for day in df[days_col].to_list()})

    if not days:
        logger.info("no days to replace in %s, skipping write", cyan(target))
        return

    predicate: str = f"{days_col} IN ({', '.join(f'DATE {day!r}' for day in days)})"

    write_deltalake(
        target,
        df.to_arrow(),
        storage_options=S3_STORAGE_OPTIONS,
        mode="overwrite",
        predicate=predicate,
        partition_by=partition_by or [],
    )

    logger.info(
        "replaced %s day(s) in %s (%s rows)",
        magenta(len(days)),
        cyan(target),
        magenta(len(df)),
    )


def filter_scd1(
    lf: LazyFrame,
    target: str,
    id_col: str,
    track_col: str,
) -> LazyFrame:
    """
    Filter a LazyFrame to only new/changed rows for SCD Type 1 upsert.

    Anti-joins on `(id_col, track_col)` against the existing Delta table.
    If the table doesn't exist yet (first run), returns the original
    LazyFrame unchanged, meaning all rows are new.

    This function is purely lazy, no data is materialized. The caller
    should chain this before a single `.collect()` along with validation.
    """
    try:
        DeltaTable(target, storage_options=S3_STORAGE_OPTIONS)
    except TableNotFoundError:
        # first run: table doesn't exist yet, all rows are new
        return lf

    # truly lazy scan, only the 2 columns needed for the anti-join
    existing: LazyFrame = pl.scan_delta(target, storage_options=S3_STORAGE_OPTIONS).select(
        id_col, track_col
    )

    return lf.join(existing, on=[id_col, track_col], how="anti")


__all__: list[str] = ["append_delta", "filter_scd1", "replace_days_delta"]
