"""Tests for Silver layer Pandera contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import polars.dataframe.frame
import pytest
from pandera.errors import SchemaError
from pandera.typing.polars import DataFrame

from core.contracts.silver import (
    ActorsContract,
    OrgsContract,
    ReposContract,
    SilverEventsContract,
)


class TestSilverEventsContract:
    """Validates the SilverEventsContract schema rules."""

    @pytest.mark.contract
    def test_valid_data_passes(self, sample_silver_events_df: pl.DataFrame) -> None:
        """A DataFrame matching all contract rules must pass validation."""
        result: DataFrame[SilverEventsContract] = SilverEventsContract.validate(
            check_obj=sample_silver_events_df
        )
        assert result is not None
        assert len(result) == 3  # noqa: PLR2004

    @pytest.mark.contract
    def test_unknown_event_type_raises_error(self, sample_silver_events_df: pl.DataFrame) -> None:
        """An event type not in KNOWN_EVENT_TYPES must be rejected."""
        df: pl.DataFrame = sample_silver_events_df.with_columns(
            pl.lit(value="UnknownEvent").alias(name="type")
        )
        with pytest.raises(expected_exception=SchemaError, match="isin"):
            SilverEventsContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_unknown_action_raises_error(self, sample_silver_events_df: pl.DataFrame) -> None:
        """An action not in KNOWN_ACTIONS must be rejected."""
        df: pl.DataFrame = sample_silver_events_df.with_columns(
            pl.lit(value="invalid_action_xyz").alias(name="action")
        )
        with pytest.raises(expected_exception=SchemaError, match="isin"):
            SilverEventsContract.validate(check_obj=df)

    @pytest.mark.contract
    @pytest.mark.parametrize(
        argnames="null_column", argvalues=["id", "type", "action", "actor_id", "repo_id"]
    )
    def test_null_required_field_raises_error(
        self, sample_silver_events_df: pl.DataFrame, null_column: str
    ) -> None:
        """Any null in a required field must raise SchemaError."""
        df: pl.DataFrame = sample_silver_events_df.with_columns(
            pl.lit(value=None).alias(name=null_column)
        )
        with pytest.raises(expected_exception=SchemaError, match="nullable"):
            SilverEventsContract.validate(check_obj=df)

    @pytest.mark.contract
    def test_negative_id_raises_error(self, sample_silver_events_df: pl.DataFrame) -> None:
        """id must be >= 0 (ge=0 constraint)."""
        df: pl.DataFrame = sample_silver_events_df.head(n=1).with_columns(
            pl.lit(value=-1).cast(dtype=pl.Int64).alias(name="id")
        )
        with pytest.raises(expected_exception=SchemaError, match="greater_than_or_equal_to"):
            SilverEventsContract.validate(check_obj=df)


class TestActorsContract:
    """Validates the ActorsContract schema rules."""

    @pytest.mark.contract
    def test_valid_data_passes(self) -> None:
        """A valid actors DataFrame must pass validation."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=[100, 200], dtype=pl.Int64),
                "login": pl.Series(name=["user1", "user2"], dtype=pl.String),
                "display_login": pl.Series(name=["User One", None], dtype=pl.String),
                "gravatar_id": pl.Series(name=["", None], dtype=pl.String),
                "url": pl.Series(
                    name=[
                        "https://api.github.com/users/user1",
                        "https://api.github.com/users/user2",
                    ],
                    dtype=pl.String,
                ),
                "avatar_url": pl.Series(name=["https://avatars.com/u/100", None], dtype=pl.String),
                "is_bot": pl.Series(name=[False, False], dtype=pl.Boolean),
                "first_seen_at": pl.Series(
                    name=[
                        datetime(
                            year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC
                        ),
                        datetime(
                            year=2026, month=7, day=19, hour=11, minute=0, second=0, tzinfo=UTC
                        ),
                    ],
                    dtype=pl.Datetime,
                ),
                "inserted_at": pl.Series(
                    name=[
                        datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0),
                        datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0),
                    ],
                    dtype=pl.Datetime,
                ),
            }
        )
        result: DataFrame[ActorsContract] = ActorsContract.validate(check_obj=df)
        assert result is not None

    @pytest.mark.contract
    def test_bot_detection_field_is_boolean(self) -> None:
        """is_bot must be a boolean column."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=[300], dtype=pl.Int64),
                "login": pl.Series(name=["bot[bot]"], dtype=pl.String),
                "display_login": pl.Series(name=[None], dtype=pl.String),
                "gravatar_id": pl.Series(name=[None], dtype=pl.String),
                "url": pl.Series(name=["https://api.github.com/users/bot"], dtype=pl.String),
                "avatar_url": pl.Series(name=[None], dtype=pl.String),
                "is_bot": pl.Series(name=[True], dtype=pl.Boolean),
                "first_seen_at": pl.Series(
                    name=[
                        datetime(
                            year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC
                        )
                    ],
                    dtype=pl.Datetime,
                ),
                "inserted_at": pl.Series(
                    name=[datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0)],
                    dtype=pl.Datetime,
                ),
            }
        )
        result: DataFrame[ActorsContract] = ActorsContract.validate(check_obj=df)
        assert result["is_bot"][0] is True


class TestReposContract:
    """Validates the ReposContract schema rules."""

    @pytest.mark.contract
    def test_valid_data_passes(self) -> None:
        """A valid repos DataFrame must pass validation."""
        df = pl.DataFrame(
            data={
                "id": [10, 20],
                "name": ["org/repo1", "org/repo2"],
                "url": [
                    "https://api.github.com/repos/org/repo1",
                    "https://api.github.com/repos/org/repo2",
                ],
                "first_seen_at": [
                    datetime(year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC),
                    datetime(year=2026, month=7, day=19, hour=11, minute=0, second=0, tzinfo=UTC),
                ],
                "inserted_at": [
                    datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0),
                    datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0),
                ],
            }
        )
        result: DataFrame[ReposContract] = ReposContract.validate(check_obj=df)
        assert result is not None

    @pytest.mark.contract
    def test_null_name_raises_error(self) -> None:
        """name is required (non-nullable)."""
        df = pl.DataFrame(
            data={
                "id": [10],
                "name": [None],
                "url": ["https://api.github.com/repos/org/repo1"],
                "first_seen_at": [
                    datetime(year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC)
                ],
                "inserted_at": [datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0)],
            }
        )
        with pytest.raises(expected_exception=SchemaError, match="nullable"):
            ReposContract.validate(check_obj=df)


class TestOrgsContract:
    """Validates the OrgsContract schema rules."""

    @pytest.mark.contract
    def test_valid_data_passes(self) -> None:
        """A valid orgs DataFrame must pass validation."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=[1], dtype=pl.Int64),
                "login": pl.Series(name=["org1"], dtype=pl.String),
                "gravatar_id": pl.Series(name=[None], dtype=pl.String),
                "url": pl.Series(name=["https://api.github.com/orgs/org1"], dtype=pl.String),
                "avatar_url": pl.Series(name=[None], dtype=pl.String),
                "first_seen_at": pl.Series(
                    name=[
                        datetime(
                            year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC
                        )
                    ],
                    dtype=pl.Datetime,
                ),
                "inserted_at": pl.Series(
                    name=[datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0)],
                    dtype=pl.Datetime,
                ),
            }
        )
        result: DataFrame[OrgsContract] = OrgsContract.validate(check_obj=df)
        assert result is not None
