"""Tests for Gold layer Pandera contracts."""

from __future__ import annotations

import polars as pl
import polars.dataframe.frame
import pytest
from pandera.errors import SchemaError
from pandera.typing.polars import DataFrame

from core.contracts.gold import GoldDailyContract


class TestGoldDailyContract:
    """Validates the GoldDailyContract schema rules."""

    @pytest.mark.contract
    def test_valid_data_passes(self, sample_gold_daily_df: pl.DataFrame) -> None:
        """A DataFrame matching all contract rules must pass validation."""
        result: DataFrame[GoldDailyContract] = GoldDailyContract.validate(
            check_obj=sample_gold_daily_df
        )
        assert result is not None
        assert len(result) == 1

    @pytest.mark.contract
    def test_score_above_100_raises_error(self, sample_gold_daily_df: pl.DataFrame) -> None:
        """gitpulse_score is capped at 100 (le=100)."""
        df: pl.DataFrame = sample_gold_daily_df.with_columns(
            pl.lit(value=150.0).alias(name="gitpulse_score")
        )
        with pytest.raises(expected_exception=SchemaError, match="less_than_or_equal_to"):
            GoldDailyContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_score_negative_raises_error(self, sample_gold_daily_df: pl.DataFrame) -> None:
        """gitpulse_score must be >= 0."""
        df: pl.DataFrame = sample_gold_daily_df.with_columns(
            pl.lit(value=-5.0).alias(name="gitpulse_score")
        )
        with pytest.raises(expected_exception=SchemaError, match="greater_than_or_equal_to"):
            GoldDailyContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_negative_event_count_raises_error(self, sample_gold_daily_df: pl.DataFrame) -> None:
        """Event count fields must be >= 0."""
        df: pl.DataFrame = sample_gold_daily_df.with_columns(
            pl.lit(value=-1).cast(dtype=pl.Int64).alias(name="total_events")
        )
        with pytest.raises(expected_exception=SchemaError, match="greater_than_or_equal_to"):
            GoldDailyContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_pr_merge_rate_out_of_range_raises_error(
        self, sample_gold_daily_df: pl.DataFrame
    ) -> None:
        """pr_merge_rate must be between 0.0 and 1.0."""
        df: pl.DataFrame = sample_gold_daily_df.with_columns(
            pl.lit(value=1.5).alias(name="pr_merge_rate")
        )
        with pytest.raises(expected_exception=SchemaError, match="less_than_or_equal_to"):
            GoldDailyContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_null_org_id_is_allowed(self, sample_gold_daily_df: pl.DataFrame) -> None:
        """org_id is nullable and may be None."""
        df: pl.DataFrame = sample_gold_daily_df.with_columns(
            pl.lit(value=None).cast(dtype=pl.Int64).alias(name="org_id")
        )
        result: DataFrame[GoldDailyContract] = GoldDailyContract.validate(check_obj=df)
        assert result is not None

    @pytest.mark.contract
    def test_wrong_partition_format_raises_error(self, sample_gold_daily_df: pl.DataFrame) -> None:
        """Partition column 'month' must match regex ^(0[1-9]|1[0-2])$."""
        df: pl.DataFrame = sample_gold_daily_df.with_columns(
            pl.lit(value="13").alias(name="month")  # invalid month
        )
        with pytest.raises(expected_exception=SchemaError, match="str_matches"):
            GoldDailyContract.validate(check_obj=df)
