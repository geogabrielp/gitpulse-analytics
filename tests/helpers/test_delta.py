"""
Tests for Delta Lake helper functions.

Note: Delta tests use local filesystem paths instead of S3/MinIO because
the delta-rs library uses its own Rust-based S3 client that is NOT
intercepted by moto's mock_aws. Local paths are faster and more reliable
for unit testing the core logic of append_delta and filter_scd1.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from deltalake import DeltaTable, write_deltalake
from polars.dataframe.frame import DataFrame
from polars.lazyframe.frame import LazyFrame

from core.helpers.delta import append_delta, filter_scd1, replace_days_delta


class TestAppendDelta:
    """Test the append_delta helper using local Delta tables."""

    @pytest.mark.helper
    def test_creates_table_if_not_exists(self, tmp_path: Path) -> None:
        """When a Delta table doesn't exist, append_delta must create it."""
        target = str(object=tmp_path / "test_events")
        df = pl.DataFrame(data={"id": [1, 2, 3], "value": ["a", "b", "c"]})

        append_delta(df=df, target=target)

        result: DataFrame = pl.read_delta(source=target)
        assert len(result) == 3  # noqa: PLR2004
        assert set(result["id"].to_list()) == {1, 2, 3}

    @pytest.mark.helper
    def test_appends_to_existing_table(self, tmp_path: Path) -> None:
        """When a Delta table exists, append_delta must add rows."""
        target = str(object=tmp_path / "test_events")
        df = pl.DataFrame(data={"id": [1, 2], "value": ["a", "b"]})

        append_delta(df=df, target=target)
        append_delta(df=df, target=target)

        result: DataFrame = pl.read_delta(source=target)
        assert len(result) == 4  # 2 + 2  # noqa: PLR2004

    @pytest.mark.helper
    def test_appends_empty_dataframe(self, tmp_path: Path) -> None:
        """Appending an empty DataFrame must create table with zero rows."""
        target = str(object=tmp_path / "test_empty")
        empty_df = pl.DataFrame(
            data={
                "id": pl.Series(name=[], dtype=pl.Int64),
                "value": pl.Series(name=[], dtype=pl.String),
            }
        )

        append_delta(df=empty_df, target=target)

        result: DataFrame = pl.read_delta(source=target)
        assert len(result) == 0

    @pytest.mark.helper
    def test_with_partition_by(self, tmp_path: Path) -> None:
        """Partitioning by a column must create Delta partitions."""
        target = str(object=tmp_path / "test_partitioned")
        df = pl.DataFrame(
            data={
                "id": [1, 2, 3],
                "category": ["A", "B", "A"],
                "value": ["x", "y", "z"],
            }
        )

        append_delta(df=df, target=target, partition_by=["category"])

        dt = DeltaTable(table_uri=target)
        assert len(dt.metadata().partition_columns) == 1
        assert dt.metadata().partition_columns[0] == "category"


class TestFilterSCD1:
    """Test the SCD Type 1 anti-join filter using local Delta tables."""

    @pytest.mark.helper
    def test_returns_all_rows_when_table_not_exists(self, tmp_path: Path) -> None:
        """When the target Delta table doesn't exist, all rows must pass through."""
        target = str(object=tmp_path / "test_actors")
        lf: LazyFrame = pl.DataFrame(
            data={"id": [1, 2, 3], "login": ["alice", "bob", "charlie"]}
        ).lazy()
        result: DataFrame = filter_scd1(
            lf=lf, target=target, id_col="id", track_col="login"
        ).collect()
        assert len(result) == 3  # noqa: PLR2004

    @pytest.mark.helper
    def test_filters_existing_combinations(self, tmp_path: Path) -> None:
        """Rows with (id, login) already in the target must be removed."""
        target = str(object=tmp_path / "test_actors")

        # First, write existing data directly
        existing = pl.DataFrame(data={"id": [1, 2], "login": ["alice", "bob"]})
        write_deltalake(table_or_uri=target, data=existing.to_arrow())

        # Now try with some new and some duplicate combinations
        new_data: LazyFrame = pl.DataFrame(
            data={"id": [1, 2, 3], "login": ["alice", "bob_updated", "charlie"]}
        ).lazy()

        result: DataFrame = filter_scd1(
            lf=new_data, target=target, id_col="id", track_col="login"
        ).collect()

        assert len(result) == 2  # (2, bob_updated) and (3, charlie) are new  # noqa: PLR2004
        assert (1, "alice") not in {tuple(r) for r in result.select("id", "login").rows()}

    @pytest.mark.helper
    def test_all_new_rows_pass_through(self, tmp_path: Path) -> None:
        """When no existing combination matches, all new rows must pass through."""
        target = str(object=tmp_path / "test_actors")

        existing = pl.DataFrame(data={"id": [1], "login": ["alice"]})
        write_deltalake(table_or_uri=target, data=existing.to_arrow())

        new_data: LazyFrame = pl.DataFrame(data={"id": [2, 3], "login": ["bob", "charlie"]}).lazy()

        result: DataFrame = filter_scd1(
            lf=new_data, target=target, id_col="id", track_col="login"
        ).collect()

        assert len(result) == 2  # noqa: PLR2004

    @pytest.mark.helper
    def test_unchanged_rows_are_filtered_out(self, tmp_path: Path) -> None:
        """When (id, track_col) already exists exactly, those rows must be removed."""
        target = str(object=tmp_path / "test_actors")

        existing = pl.DataFrame(data={"id": [1], "login": ["alice"]})
        write_deltalake(table_or_uri=target, data=existing.to_arrow())

        new_data: LazyFrame = pl.DataFrame(data={"id": [1], "login": ["alice"]}).lazy()

        result: DataFrame = filter_scd1(
            lf=new_data, target=target, id_col="id", track_col="login"
        ).collect()

        assert result.is_empty()

    @pytest.mark.helper
    def test_different_track_col_value_passes_through(self, tmp_path: Path) -> None:
        """Same id but different track_col value must pass through (SCD1 update)."""
        target = str(object=tmp_path / "test_actors")

        existing = pl.DataFrame(data={"id": [1], "login": ["alice"]})
        write_deltalake(table_or_uri=target, data=existing.to_arrow())

        new_data: LazyFrame = pl.DataFrame(data={"id": [1], "login": ["alice_updated"]}).lazy()

        result: DataFrame = filter_scd1(
            lf=new_data, target=target, id_col="id", track_col="login"
        ).collect()

        assert len(result) == 1  # (1, alice_updated) is a change


def _daily_df(days: list[date], value: int) -> DataFrame:
    """Build a Gold-like DataFrame: one row per day, partition columns included."""
    return pl.DataFrame(
        data={
            "day": days,
            "year": [str(day.year) for day in days],
            "month": [f"{day.month:02d}" for day in days],
            "total_events": [value] * len(days),
        }
    )


class TestReplaceDaysDelta:
    """Test the day-level replace helper using local Delta tables."""

    @pytest.mark.helper
    def test_creates_table_when_missing(self, tmp_path: Path) -> None:
        """replace_days_delta must create the table, partitioned, on first write."""
        target = str(tmp_path / "gold")

        replace_days_delta(
            df=_daily_df([date(2026, 10, 7)], 5), target=target, partition_by=["year", "month"]
        )

        result: DataFrame = pl.read_delta(source=target)
        assert result.height == 1
        assert DeltaTable(table_uri=target).metadata().partition_columns == ["year", "month"]

    @pytest.mark.helper
    def test_replaces_only_the_given_days(self, tmp_path: Path) -> None:
        """Days absent from the DataFrame must survive untouched."""
        target = str(tmp_path / "gold")
        days = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
        append_delta(df=_daily_df(days, 1), target=target, partition_by=["year", "month"])

        replace_days_delta(
            df=_daily_df([date(2026, 10, 7)], 99), target=target, partition_by=["year", "month"]
        )

        result: DataFrame = pl.read_delta(source=target).sort("day")
        assert result["total_events"].to_list() == [1, 1, 99]
        assert len(result) == 3  # noqa: PLR2004

    @pytest.mark.helper
    def test_is_idempotent(self, tmp_path: Path) -> None:
        """Replacing the same days with the same rows must not grow the table."""
        target = str(tmp_path / "gold")
        df = _daily_df([date(2026, 10, 7)], 99)

        replace_days_delta(df=df, target=target, partition_by=["year", "month"])
        replace_days_delta(df=df, target=target, partition_by=["year", "month"])

        result: DataFrame = pl.read_delta(source=target)
        assert result.height == 1
        assert result["total_events"].to_list() == [99]

    @pytest.mark.helper
    def test_drops_previous_duplicates_of_the_replaced_day(self, tmp_path: Path) -> None:
        """A day already duplicated in the table must come back as a single copy."""
        target = str(tmp_path / "gold")
        day = date(2026, 10, 7)
        for _ in range(2):
            append_delta(df=_daily_df([day], 1), target=target, partition_by=["year", "month"])
        assert pl.read_delta(source=target).height == 2  # noqa: PLR2004

        replace_days_delta(df=_daily_df([day], 50), target=target, partition_by=["year", "month"])

        result: DataFrame = pl.read_delta(source=target)
        assert result.height == 1
        assert result["total_events"].to_list() == [50]

    @pytest.mark.helper
    def test_keeps_days_between_replaced_days(self, tmp_path: Path) -> None:
        """Replacing 2 non-adjacent days must not delete the day in between.

        This is the reason the predicate is an IN list rather than a BETWEEN
        range: a range would silently drop 2026-10-07.
        """
        target = str(tmp_path / "gold")
        days = [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]
        append_delta(df=_daily_df(days, 1), target=target, partition_by=["year", "month"])

        replace_days_delta(
            df=_daily_df([date(2026, 10, 6), date(2026, 10, 8)], 7),
            target=target,
            partition_by=["year", "month"],
        )

        result: DataFrame = pl.read_delta(source=target).sort("day")
        assert result["day"].to_list() == days
        assert result["total_events"].to_list() == [7, 1, 7]

    @pytest.mark.helper
    def test_empty_dataframe_writes_nothing(self, tmp_path: Path) -> None:
        """An empty DataFrame must be a no-op, not a malformed predicate."""
        target = str(tmp_path / "gold")
        append_delta(
            df=_daily_df([date(2026, 10, 7)], 1), target=target, partition_by=["year", "month"]
        )

        empty = pl.DataFrame(
            schema={
                "day": pl.Date,
                "year": pl.String,
                "month": pl.String,
                "total_events": pl.Int64,
            }
        )
        replace_days_delta(df=empty, target=target, partition_by=["year", "month"])

        result: DataFrame = pl.read_delta(source=target)
        assert result.height == 1
        assert result["total_events"].to_list() == [1]
