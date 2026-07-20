"""
Tests for Delta Lake helper functions.

Note: Delta tests use local filesystem paths instead of S3/MinIO because
the delta-rs library uses its own Rust-based S3 client that is NOT
intercepted by moto's mock_aws. Local paths are faster and more reliable
for unit testing the core logic of append_delta and filter_scd1.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from deltalake import DeltaTable, write_deltalake
from polars.dataframe.frame import DataFrame
from polars.lazyframe.frame import LazyFrame

from core.helpers.delta import append_delta, filter_scd1


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
