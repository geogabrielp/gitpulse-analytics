"""Tests for Bronze layer Pandera contracts."""

from __future__ import annotations

import polars as pl
import polars.dataframe.frame
import pytest
from pandera.errors import SchemaError
from pandera.typing.polars import DataFrame

from core.contracts.bronze import BronzeEventsContract


class TestBronzeEventsContract:
    """Validates the BronzeEventsContract schema rules."""

    @pytest.mark.contract
    def test_valid_data_passes(self, sample_bronze_df: pl.DataFrame) -> None:
        """A DataFrame matching all contract rules must pass validation."""
        result: DataFrame[BronzeEventsContract] = BronzeEventsContract.validate(
            check_obj=sample_bronze_df
        )
        assert result is not None
        assert len(result) == 3  # noqa: PLR2004

    @pytest.mark.contract
    @pytest.mark.parametrize(argnames="null_column", argvalues=["id", "type", "created_at"])
    def test_null_required_field_raises_error(
        self, sample_bronze_df: pl.DataFrame, null_column: str
    ) -> None:
        """Any null in a required (non-nullable) field must raise SchemaError."""
        df: pl.DataFrame = sample_bronze_df.with_columns(
            pl.lit(value=None).alias(name=null_column),
        )
        with pytest.raises(expected_exception=SchemaError, match="nullable"):
            BronzeEventsContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_null_optional_fields_are_allowed(self, sample_bronze_df: pl.DataFrame) -> None:
        """Fields not declared in the contract (actor, repo, etc.) may be null."""
        df: pl.DataFrame = sample_bronze_df.with_columns(
            pl.lit(value=None).alias(name="actor"),
            pl.lit(value=None).alias(name="repo"),
        )
        result: DataFrame[BronzeEventsContract] = BronzeEventsContract.validate(check_obj=df)
        assert result is not None

    @pytest.mark.contract
    def test_unknown_event_type_is_allowed(self, sample_bronze_df: pl.DataFrame) -> None:
        """Bronze does NOT constrain event types, unknown types must pass."""
        df: pl.DataFrame = sample_bronze_df.with_columns(
            pl.lit(value="NewfangledEvent").alias(name="type")
        )
        result: DataFrame[BronzeEventsContract] = BronzeEventsContract.validate(check_obj=df)
        assert result is not None

    @pytest.mark.contract
    def test_wrong_dtype_raises_error(self, sample_bronze_df: pl.DataFrame) -> None:
        """If a column has the wrong data type, validation must fail."""
        df: pl.DataFrame = sample_bronze_df.with_columns(
            pl.lit(value=42).cast(dtype=pl.Int64).alias(name="id")  # id should be String
        )
        with pytest.raises(
            expected_exception=SchemaError, match="expected column.*id.*to have type String"
        ):
            BronzeEventsContract.validate(check_obj=df)
