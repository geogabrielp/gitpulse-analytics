"""Tests for Silver layer transformations (bronze_to_silver.py)."""

from __future__ import annotations

import polars as pl
import pytest
from polars.dataframe.frame import DataFrame
from polars.lazyframe.frame import LazyFrame

from core.transforms.bronze_to_silver import (
    _build_actors,
    _build_events,
    _extract_action,
    _filter_events,
    _parse_structs,
)


def _add_ingestion_cols(df: pl.DataFrame) -> pl.DataFrame:
    """Add source_file and ingestion_timestamp columns required by _filter_events."""
    return df.with_columns(
        source_file=pl.lit(value="test/path/file.json.gz"),
        ingestion_timestamp=pl.lit(value="2026-07-19T12:00:00Z"),
    )


class TestFilterEvents:
    """Test that only KNOWN_EVENT_TYPES pass the filter."""

    @pytest.mark.transform
    def test_keeps_known_types(self, sample_bronze_df: pl.DataFrame) -> None:
        """All rows with known event types must be kept."""
        df: DataFrame = _add_ingestion_cols(sample_bronze_df)
        result: DataFrame = _filter_events(lf=df.lazy()).collect()
        assert result.height == 3  # noqa: PLR2004

    @pytest.mark.transform
    def test_removes_unknown_types(self, sample_bronze_df: pl.DataFrame) -> None:
        """Rows with unknown event types must be filtered out."""
        df: DataFrame = _add_ingestion_cols(sample_bronze_df).with_columns(
            pl.lit(value="TotallyUnknownEvent").alias(name="type")
        )
        result: DataFrame = _filter_events(lf=df.lazy()).collect()
        assert result.height == 0

    @pytest.mark.transform
    def test_mixed_types_keeps_only_known(self, sample_bronze_df: pl.DataFrame) -> None:
        """When mixing known and unknown types, only known types remain."""
        df: DataFrame = _add_ingestion_cols(
            df=pl.concat(
                items=[
                    sample_bronze_df,
                    sample_bronze_df.with_columns(pl.lit(value="GollumEvent").alias(name="type")),
                ]
            )
        )
        result: DataFrame = _filter_events(lf=df.lazy()).collect()
        assert result.height == 3  # noqa: PLR2004

    @pytest.mark.transform
    def test_drops_ingestion_columns(self, sample_bronze_df: pl.DataFrame) -> None:
        """Columns source_file and ingestion_timestamp must be dropped."""
        df: DataFrame = _add_ingestion_cols(sample_bronze_df)
        result: DataFrame = _filter_events(lf=df.lazy()).collect()
        assert "source_file" not in result.columns
        assert "ingestion_timestamp" not in result.columns


class TestParseStructs:
    """Test JSON decoding of actor, repo, and org columns."""

    @pytest.mark.transform
    def test_decodes_actor_repo_org(self, sample_bronze_df: pl.DataFrame) -> None:
        """JSON strings must be decoded into struct columns."""
        result: DataFrame = _parse_structs(lf=sample_bronze_df.lazy()).collect()
        assert "actor_struct" in result.columns
        assert "repo_struct" in result.columns
        assert "org_struct" in result.columns
        assert "actor" not in result.columns
        assert "repo" not in result.columns
        assert "org" not in result.columns

    @pytest.mark.transform
    def test_parses_timestamps(self, sample_bronze_df: pl.DataFrame) -> None:
        """created_at must be converted from string to datetime."""
        result: DataFrame = _parse_structs(lf=sample_bronze_df.lazy()).collect()
        assert result["created_at"].dtype == pl.Datetime

    @pytest.mark.transform
    def test_deduplicates_by_id(self, sample_bronze_df: pl.DataFrame) -> None:
        """Duplicate ids must be reduced to a single row."""
        df: DataFrame = pl.concat(items=[sample_bronze_df, sample_bronze_df])
        result: DataFrame = _parse_structs(lf=df.lazy()).collect()
        # 3 unique ids, duplicates removed
        assert result.height == 3  # noqa: PLR2004

    @pytest.mark.transform
    def test_null_org_becomes_null_struct(self, sample_bronze_df: pl.DataFrame) -> None:
        """A null org JSON string should produce a null org_struct."""
        result: DataFrame = _parse_structs(lf=sample_bronze_df.lazy()).collect()
        null_org_row: DataFrame = result.filter(pl.col(name="id") == "3")
        assert len(null_org_row) == 1
        assert null_org_row["org_struct"][0] is None


class TestExtractAction:
    """Test action extraction/synthesis from event payloads."""

    @pytest.mark.transform
    def test_push_event_gets_pushed(self, sample_bronze_df: pl.DataFrame) -> None:
        """PushEvent must synthesize action='pushed'."""
        df: DataFrame = sample_bronze_df.head(n=1)  # first row is PushEvent
        parsed: LazyFrame = _parse_structs(lf=df.lazy())
        result: DataFrame = _extract_action(lf=parsed).collect()
        assert result["action"][0] == "pushed"

    @pytest.mark.transform
    def test_create_event_gets_created(self) -> None:
        """CreateEvent must synthesize action='created'."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=["evt_010"], dtype=pl.String),
                "type": pl.Series(name=["CreateEvent"], dtype=pl.String),
                "actor": pl.Series(
                    name=[
                        '{"id":1,"login":"u","display_login":"U","gravatar_id":"","url":"","avatar_url":""}'
                    ],
                    dtype=pl.String,
                ),
                "repo": pl.Series(name=['{"id":1,"name":"r","url":""}'], dtype=pl.String),
                "payload": pl.Series(name=['{"ref":"main","ref_type":"branch"}'], dtype=pl.String),
                "public": pl.Series(name=[True], dtype=pl.Boolean),
                "created_at": pl.Series(name=["2026-07-19T10:00:00Z"], dtype=pl.String),
                "org": pl.Series(name=[None], dtype=pl.String),
            }
        )
        parsed: LazyFrame = _parse_structs(lf=df.lazy())
        result: DataFrame = _extract_action(lf=parsed).collect()
        assert result["action"][0] == "created"

    @pytest.mark.transform
    def test_delete_event_gets_deleted(self) -> None:
        """DeleteEvent must synthesize action='deleted'."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=["evt_011"], dtype=pl.String),
                "type": pl.Series(name=["DeleteEvent"], dtype=pl.String),
                "actor": pl.Series(
                    name=[
                        '{"id":1,"login":"u","display_login":"U","gravatar_id":"","url":"","avatar_url":""}'
                    ],
                    dtype=pl.String,
                ),
                "repo": pl.Series(name=['{"id":1,"name":"r","url":""}'], dtype=pl.String),
                "payload": pl.Series(
                    name=['{"ref":"feature-branch","ref_type":"branch"}'], dtype=pl.String
                ),
                "public": pl.Series(name=[True], dtype=pl.Boolean),
                "created_at": pl.Series(name=["2026-07-19T10:00:00Z"], dtype=pl.String),
                "org": pl.Series(name=[None], dtype=pl.String),
            }
        )
        parsed: LazyFrame = _parse_structs(lf=df.lazy())
        result: DataFrame = _extract_action(lf=parsed).collect()
        assert result["action"][0] == "deleted"

    @pytest.mark.transform
    def test_extracts_action_from_payload(self) -> None:
        """Events with action in payload JSON must extract it correctly."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=["evt_012"], dtype=pl.String),
                "type": pl.Series(name=["IssuesEvent"], dtype=pl.String),
                "actor": pl.Series(
                    name=[
                        '{"id":1,"login":"u","display_login":"U","gravatar_id":"","url":"","avatar_url":""}'
                    ],
                    dtype=pl.String,
                ),
                "repo": pl.Series(name=['{"id":1,"name":"r","url":""}'], dtype=pl.String),
                "payload": pl.Series(name=['{"action":"opened"}'], dtype=pl.String),
                "public": pl.Series(name=[True], dtype=pl.Boolean),
                "created_at": pl.Series(name=["2026-07-19T10:00:00Z"], dtype=pl.String),
                "org": pl.Series(name=[None], dtype=pl.String),
            }
        )
        parsed: LazyFrame = _parse_structs(lf=df.lazy())
        result: DataFrame = _extract_action(lf=parsed).collect()
        assert result["action"][0] == "opened"


class TestBuildEvents:
    """Test building the events fact table."""

    @pytest.mark.transform
    def test_partition_columns_present(self, sample_bronze_df: pl.DataFrame) -> None:
        """year, month, day, hour partition columns must exist with correct values."""
        parsed: LazyFrame = _parse_structs(lf=sample_bronze_df.lazy())
        extracted: LazyFrame = _extract_action(lf=parsed)
        result: DataFrame = _build_events(df=extracted).collect()
        expected_columns: set[str] = {"year", "month", "day", "hour"}
        assert expected_columns.issubset(result.columns)
        assert set(result["year"].to_list()) == {"2026"}
        assert set(result["month"].to_list()) == {"07"}
        assert set(result["day"].to_list()) == {"19"}
        assert set(result["hour"].to_list()) == {"10", "11", "12"}

    @pytest.mark.transform
    def test_id_casted_to_int64(self, sample_bronze_df: pl.DataFrame) -> None:
        """Event id must be cast from String to Int64."""
        parsed: LazyFrame = _parse_structs(lf=sample_bronze_df.lazy())
        extracted: LazyFrame = _extract_action(lf=parsed)
        result: DataFrame = _build_events(df=extracted).collect()
        assert result["id"].dtype == pl.Int64

    @pytest.mark.transform
    def test_drops_null_ids(self) -> None:
        """Rows with null id, actor_id, or repo_id must be dropped."""
        df = pl.DataFrame(
            data={
                "id": pl.Series(name=["1"], dtype=pl.String),
                "type": pl.Series(name=["PushEvent"], dtype=pl.String),
                "actor": pl.Series(
                    name=[
                        '{"id":null,"login":"unknown","display_login":"","gravatar_id":"","url":"","avatar_url":""}'
                    ],
                    dtype=pl.String,
                ),
                "repo": pl.Series(name=['{"id":null,"name":"orphan","url":""}'], dtype=pl.String),
                "payload": pl.Series(name=["{}"], dtype=pl.String),
                "public": pl.Series(name=[True], dtype=pl.Boolean),
                "created_at": pl.Series(name=["2026-07-19T10:00:00Z"], dtype=pl.String),
                "org": pl.Series(name=[None], dtype=pl.String),
            }
        )
        parsed: LazyFrame = _parse_structs(lf=df.lazy())
        extracted: LazyFrame = _extract_action(lf=parsed)
        result: DataFrame = _build_events(df=extracted).collect()
        assert result.is_empty()


class TestBuildActors:
    """Test building the actors dimension."""

    @pytest.mark.transform
    def test_bot_detection(self, sample_bronze_df: pl.DataFrame) -> None:
        """Actors with [bot] in login must be flagged as is_bot=True."""
        parsed: LazyFrame = _parse_structs(lf=sample_bronze_df.lazy())
        result: DataFrame = _build_actors(df=parsed).collect()
        bot_rows: DataFrame = result.filter(pl.col(name="is_bot") == True)  # noqa: E712
        assert bot_rows.height == 1
        assert bot_rows["login"][0] == "bot[bot]"

    @pytest.mark.transform
    def test_non_bot_not_flagged(self, sample_bronze_df: pl.DataFrame) -> None:
        """Regular users must have is_bot=False."""
        parsed: LazyFrame = _parse_structs(lf=sample_bronze_df.lazy())
        result: DataFrame = _build_actors(df=parsed).collect()
        non_bot: DataFrame = result.filter(pl.col(name="is_bot") == False)  # noqa: E712
        assert non_bot.height >= 2  # noqa: PLR2004

    @pytest.mark.transform
    def test_actors_grouped_by_id_and_login(self, sample_bronze_df: pl.DataFrame) -> None:
        """Actors must be grouped by (id, login), producing unique versions."""
        parsed: LazyFrame = _parse_structs(lf=sample_bronze_df.lazy())
        result: DataFrame = _build_actors(df=parsed).collect()
        # 3 unique (id, login) pairs from sample
        assert result.height == 3  # noqa: PLR2004
        # Verify no duplicates
        assert result.unique(subset=["id", "login"]).height == result.height
