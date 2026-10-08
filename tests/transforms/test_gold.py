"""Tests for Gold layer transformations (silver_to_gold.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest
from deltalake import write_deltalake
from polars.dataframe.frame import DataFrame
from polars.lazyframe.frame import LazyFrame

from core.transforms import silver_to_gold
from core.transforms.silver_to_gold import (
    _build_gold_daily,
    _partition_days_range,
    _pending_days,
)


# Helper: build a Silver-like LazyFrame for testing
def _build_silver_lf(
    types: list[str],
    actions: list[str],
    repo_ids: list[int] | None = None,
    org_ids: list[int | None] | None = None,
    actor_ids: list[int] | None = None,
) -> pl.LazyFrame:
    """Create a minimal Silver events LazyFrame for gold transform testing."""
    n: int = len(types)
    if n == 0:
        return pl.LazyFrame(
            data={
                "type": pl.Series(name=[], dtype=pl.String),
                "action": pl.Series(name=[], dtype=pl.String),
                "actor_id": pl.Series(name=[], dtype=pl.Int64),
                "repo_id": pl.Series(name=[], dtype=pl.Int64),
                "org_id": pl.Series(name=[], dtype=pl.Int64),
                "created_at": pl.Series(name=[], dtype=pl.Datetime),
            }
        )

    return pl.DataFrame(
        data={
            "type": types,
            "action": actions,
            "actor_id": actor_ids or [100] * n,
            "repo_id": repo_ids or [10] * n,
            "org_id": org_ids or [1] * n,
            "created_at": [
                datetime(year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC)
            ]
            * n,
        }
    ).lazy()


class TestGitPulseScore:
    """Test the GitPulse Score formula and capping."""

    @pytest.mark.transform
    def test_score_formula_push_only(self) -> None:
        """Only PushEvents (weight=1): score = push_count * 1."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"] * 5,
            actions=["pushed"] * 5,
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["gitpulse_score"][0] == 5.0  # noqa: PLR2004

    @pytest.mark.transform
    def test_score_formula_mixed(self) -> None:
        """Push(1) + PR(5) + Issues(3) + Watch(2) = 11."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent", "PullRequestEvent", "IssuesEvent", "WatchEvent"],
            actions=["pushed", "opened", "opened", "started"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["gitpulse_score"][0] == 11.0  # noqa: PLR2004

    @pytest.mark.transform
    def test_score_capped_at_100(self) -> None:
        """Score must never exceed 100 even with many events."""
        # 30 PushEvents * 1 = 30, 15 PRs * 5 = 75 → total 105 → capped to 100
        types: list[str] = ["PushEvent"] * 30 + ["PullRequestEvent"] * 15
        actions: list[str] = ["pushed"] * 30 + ["opened"] * 15
        df: LazyFrame = _build_silver_lf(types=types, actions=actions)
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["gitpulse_score"][0] == 100.0  # noqa: PLR2004

    @pytest.mark.transform
    def test_score_is_float(self) -> None:
        """Score column must be Float64."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"],
            actions=["pushed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["gitpulse_score"].dtype == pl.Float64

    @pytest.mark.transform
    def test_zero_events_score_zero(self) -> None:
        """If there are events but none count toward score, score = 0."""
        # ForkEvent and ReleaseEvent have no weight
        df: LazyFrame = _build_silver_lf(
            types=["ForkEvent", "ReleaseEvent"],
            actions=["forked", "published"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["gitpulse_score"][0] == 0.0


class TestPRActions:
    """Test PR action breakdown and merge rate."""

    @pytest.mark.transform
    def test_prs_opened_and_merged(self) -> None:
        """Count opened and merged PR actions correctly."""
        df: LazyFrame = _build_silver_lf(
            types=["PullRequestEvent"] * 3,
            actions=["opened", "opened", "merged"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["prs_opened"][0] == 2  # noqa: PLR2004
        assert result["prs_merged"][0] == 1

    @pytest.mark.transform
    def test_prs_closed_unmerged(self) -> None:
        """closed - merged = closed_unmerged (clamped to 0)."""
        df: LazyFrame = _build_silver_lf(
            types=["PullRequestEvent"] * 3,
            actions=["closed", "closed", "merged"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["prs_closed_unmerged"][0] == 1  # 2 closed - 1 merged

    @pytest.mark.transform
    def test_pr_merge_rate_calculation(self) -> None:
        """merge_rate = merged / (merged + closed_unmerged).

        Note: merged PRs also fire action=closed, so the formula computes
        prs_closed_unmerged = max(prs_closed - prs_merged, 0) to avoid
        double-counting. With 1 merged + 2 closed:
        - prs_merged=1, prs_closed=2
        - prs_closed_unmerged = max(2-1, 0) = 1
        - merge_rate = 1 / (1+1) = 0.5
        """
        df: LazyFrame = _build_silver_lf(
            types=["PullRequestEvent"] * 3,
            actions=["merged", "closed", "closed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["pr_merge_rate"][0] == 0.5  # 1 / (1 + 1)  # noqa: PLR2004

    @pytest.mark.transform
    def test_no_prs_merge_rate_is_null(self) -> None:
        """merge_rate must be None when there are no PRs."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"],
            actions=["pushed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["pr_merge_rate"][0] is None


class TestIssueActions:
    """Test issue action breakdown and close rate."""

    @pytest.mark.transform
    def test_issues_opened_and_closed(self) -> None:
        """Count opened and closed issue actions correctly."""
        df: LazyFrame = _build_silver_lf(
            types=["IssuesEvent"] * 3,
            actions=["opened", "opened", "closed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["issues_opened"][0] == 2  # noqa: PLR2004
        assert result["issues_closed"][0] == 1

    @pytest.mark.transform
    def test_issue_close_rate_calculation(self) -> None:
        """close_rate = closed / (opened + closed)."""
        df: LazyFrame = _build_silver_lf(
            types=["IssuesEvent"] * 4,
            actions=["opened", "opened", "closed", "closed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["issue_close_rate"][0] == 0.5  # 2 / (2 + 2)  # noqa: PLR2004

    @pytest.mark.transform
    def test_no_issues_close_rate_is_null(self) -> None:
        """close_rate must be None when there are no issues."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"],
            actions=["pushed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["issue_close_rate"][0] is None


class TestAggregation:
    """Test the daily aggregation structure."""

    @pytest.mark.transform
    def test_grain_is_day_repo_org(self) -> None:
        """Result must be grouped by (day, repo_id, org_id)."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"] * 3,
            actions=["pushed"] * 3,
            repo_ids=[10, 10, 20],
            org_ids=[1, 1, None],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result.height == 2  # 2 groups: (day,10,1) and (day,20,None)  # noqa: PLR2004
        assert list(result.columns) is not None

    @pytest.mark.transform
    def test_partition_columns_present(self) -> None:
        """year and month partition columns must exist."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"],
            actions=["pushed"],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert "year" in result.columns
        assert "month" in result.columns
        assert result["year"][0] == "2026"
        assert result["month"][0] == "07"

    @pytest.mark.transform
    def test_total_events_count(self) -> None:
        """total_events must match the number of input events."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"] * 7,
            actions=["pushed"] * 7,
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["total_events"][0] == 7  # noqa: PLR2004

    @pytest.mark.transform
    def test_unique_actors_count(self) -> None:
        """unique_actors must reflect distinct actor_ids."""
        df: LazyFrame = _build_silver_lf(
            types=["PushEvent"] * 3,
            actions=["pushed"] * 3,
            actor_ids=[100, 100, 200],
        )
        result: DataFrame = _build_gold_daily(lf=df)
        assert result["unique_actors"][0] == 2  # noqa: PLR2004

    @pytest.mark.transform
    def test_empty_input_returns_empty(self) -> None:
        """An empty LazyFrame must produce an empty DataFrame."""
        df: LazyFrame = _build_silver_lf(types=[], actions=[])
        result: DataFrame = _build_gold_daily(lf=df)
        assert result.is_empty()


# Helper: build a Silver-like LazyFrame including its (year, month, day) columns
def _build_silver_days_lf(datetimes: list[datetime]) -> pl.LazyFrame:
    """Create a minimal Silver events LazyFrame with the partition columns."""
    naive: list[datetime] = [moment.replace(tzinfo=None) for moment in datetimes]

    return (
        pl.DataFrame(data={"created_at": pl.Series(values=naive, dtype=pl.Datetime)})
        .with_columns(
            year=pl.col("created_at").dt.year().cast(pl.String),
            month=pl.col("created_at").dt.month().cast(pl.String).str.pad_start(2, "0"),
            day=pl.col("created_at").dt.day().cast(pl.String).str.pad_start(2, "0"),
        )
        .lazy()
    )


WATERMARK: date = date(2026, 10, 7)


class TestPendingDays:
    """Test the pending-day selection (silver_to_gold._pending_days)."""

    @pytest.mark.transform
    def test_includes_the_watermark_day(self) -> None:
        """The watermark day is reprocessed on purpose: it is still partial.

        It is the current UTC day, and Silver only ever appends hours to it, so
        skipping it here would freeze the day at whatever was aggregated first.
        """
        lf: LazyFrame = _build_silver_days_lf(
            [
                datetime(2026, 10, 7, 0, 0, 0),  # midnight — the subtle case
                datetime(2026, 10, 7, 23, 59, 59),
                datetime(2026, 10, 8, 1, 0, 0),
            ]
        )
        assert _pending_days(lf=lf, watermark=WATERMARK) == [date(2026, 10, 7), date(2026, 10, 8)]

    @pytest.mark.transform
    def test_excludes_days_before_the_watermark(self) -> None:
        """Days older than the watermark are already aggregated and must not return."""
        lf: LazyFrame = _build_silver_days_lf(
            [datetime(2026, 10, 6, 23, 59, 59), datetime(2026, 10, 7, 0, 0, 0)]
        )
        assert _pending_days(lf=lf, watermark=WATERMARK) == [date(2026, 10, 7)]

    @pytest.mark.transform
    def test_caught_up_returns_the_watermark_day(self) -> None:
        """A table in sync with Silver still has one day to rewrite, not zero."""
        lf: LazyFrame = _build_silver_days_lf([datetime(2026, 10, 7, 3, 0, 0)])
        assert _pending_days(lf=lf, watermark=WATERMARK) == [date(2026, 10, 7)]

    @pytest.mark.transform
    def test_empty_silver_returns_empty(self) -> None:
        """No Silver events at all means nothing to aggregate."""
        assert _pending_days(lf=_build_silver_days_lf([]), watermark=WATERMARK) == []

    @pytest.mark.transform
    def test_excludes_earlier_month_in_same_year(self) -> None:
        """The month part of the partition predicate must not leak earlier months."""
        lf: LazyFrame = _build_silver_days_lf(
            [datetime(2026, 9, 29, 12, 0, 0), datetime(2026, 10, 7, 12, 0, 0)]
        )
        assert _pending_days(lf=lf, watermark=WATERMARK) == [date(2026, 10, 7)]

    @pytest.mark.transform
    def test_excludes_earlier_year(self) -> None:
        """Same month and day in an earlier year must stay out."""
        lf: LazyFrame = _build_silver_days_lf(
            [datetime(2025, 10, 7, 12, 0, 0), datetime(2026, 10, 7, 12, 0, 0)]
        )
        assert _pending_days(lf=lf, watermark=WATERMARK) == [date(2026, 10, 7)]

    @pytest.mark.transform
    def test_month_boundary(self) -> None:
        """Watermark on the last day of a month must carry into the next one."""
        lf: LazyFrame = _build_silver_days_lf(
            [datetime(2026, 9, 30, 12, 0, 0), datetime(2026, 10, 1, 0, 0, 0)]
        )
        assert _pending_days(lf=lf, watermark=date(2026, 9, 30)) == [
            date(2026, 9, 30),
            date(2026, 10, 1),
        ]

    @pytest.mark.transform
    def test_year_boundary(self) -> None:
        """Watermark on the last day of a year must carry into the next one."""
        lf: LazyFrame = _build_silver_days_lf(
            [datetime(2025, 12, 31, 12, 0, 0), datetime(2026, 1, 1, 0, 0, 0)]
        )
        assert _pending_days(lf=lf, watermark=date(2025, 12, 31)) == [
            date(2025, 12, 31),
            date(2026, 1, 1),
        ]


class TestGetWatermark:
    """Test the gold watermark, including the empty-table edge case."""

    @pytest.mark.transform
    def test_missing_table_returns_backfill_sentinel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A gold table that doesn't exist yet means a full backfill."""
        monkeypatch.setattr(silver_to_gold, "GOLD_DAILY_ACTIVITY", str(tmp_path / "gold"))
        assert silver_to_gold._get_watermark() == date(2014, 12, 31)

    @pytest.mark.transform
    def test_empty_table_returns_backfill_sentinel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An existing but empty gold table must not yield a None watermark."""
        target = tmp_path / "gold"
        write_deltalake(
            table_or_uri=str(target),
            data=pl.DataFrame(schema={"day": pl.Date}).to_arrow(),
        )
        monkeypatch.setattr(silver_to_gold, "GOLD_DAILY_ACTIVITY", str(target))
        assert silver_to_gold._get_watermark() == date(2014, 12, 31)

    @pytest.mark.transform
    def test_returns_greatest_day(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The watermark is the greatest day already written."""
        target = tmp_path / "gold"
        write_deltalake(
            table_or_uri=str(target),
            data=pl.DataFrame({"day": [date(2026, 10, 5), date(2026, 10, 7)]}).to_arrow(),
        )
        monkeypatch.setattr(silver_to_gold, "GOLD_DAILY_ACTIVITY", str(target))
        assert silver_to_gold._get_watermark() == date(2026, 10, 7)


# a spread that crosses a month and a year, with days on both sides of a batch
SPREAD: list[datetime] = [
    datetime(2025, 12, 31, 12, 0, 0),
    datetime(2026, 1, 1, 0, 0, 0),
    datetime(2026, 9, 29, 12, 0, 0),
    datetime(2026, 9, 30, 12, 0, 0),
    datetime(2026, 10, 1, 12, 0, 0),
    datetime(2026, 10, 6, 12, 0, 0),
    datetime(2026, 10, 7, 12, 0, 0),
    datetime(2026, 10, 8, 12, 0, 0),
    datetime(2027, 1, 1, 12, 0, 0),
]


class TestPartitionDayRange:
    """Test the day-range partition predicate used to prune the silver read."""

    @pytest.mark.transform
    def test_single_day_range_keeps_only_that_day(self) -> None:
        """A one-day batch must select exactly one day out of the whole spread."""
        kept = (
            _build_silver_days_lf(SPREAD)
            .filter(_partition_days_range(date(2026, 10, 7), date(2026, 10, 7)))
            .select("day")
            .collect()
        )
        assert kept["day"].to_list() == ["07"]

    @pytest.mark.transform
    def test_range_across_a_month_boundary(self) -> None:
        """Both ends must be inclusive when the range spans two months."""
        kept = (
            _build_silver_days_lf(SPREAD)
            .filter(_partition_days_range(date(2026, 9, 30), date(2026, 10, 1)))
            .select("month", "day")
            .collect()
        )
        assert sorted(kept["month"].to_list()) == ["09", "10"]
        assert sorted(kept["day"].to_list()) == ["01", "30"]

    @pytest.mark.transform
    def test_range_across_a_year_boundary(self) -> None:
        """Both ends must be inclusive when the range spans two years."""
        kept = (
            _build_silver_days_lf(SPREAD)
            .filter(_partition_days_range(date(2025, 12, 31), date(2026, 1, 1)))
            .select("day", "month", "year")
            .collect()
        )
        assert sorted(kept["day"].to_list()) == ["01", "31"]

    @pytest.mark.transform
    def test_multi_day_range_keeps_every_day_within(self) -> None:
        """A 3-day batch must not clip its middle or its ends."""
        kept = (
            _build_silver_days_lf(SPREAD)
            .filter(_partition_days_range(date(2026, 10, 6), date(2026, 10, 8)))
            .select("day")
            .collect()
        )
        assert sorted(kept["day"].to_list()) == ["06", "07", "08"]


def _silver_frame(datetimes: list[datetime]) -> pl.DataFrame:
    """Build a Silver-like frame with its 4 partition columns (naive, as in Silver)."""
    naive: list[datetime] = [moment.replace(tzinfo=None) for moment in datetimes]

    return pl.DataFrame(
        data={
            "type": ["PushEvent"] * len(naive),
            "action": ["pushed"] * len(naive),
            "actor_id": list(range(100, 100 + len(naive))),
            "repo_id": [10] * len(naive),
            "org_id": [1] * len(naive),
            "created_at": pl.Series(values=naive, dtype=pl.Datetime),
        }
    ).with_columns(
        year=pl.col("created_at").dt.year().cast(pl.String),
        month=pl.col("created_at").dt.month().cast(pl.String).str.pad_start(2, "0"),
        day=pl.col("created_at").dt.day().cast(pl.String).str.pad_start(2, "0"),
        hour=pl.col("created_at").dt.hour().cast(pl.String).str.pad_start(2, "0"),
    )


class TestReadSilverEvents:
    """Test the silver read against a local Delta table (delta-rs ignores moto)."""

    @pytest.mark.transform
    def test_keeps_only_the_batch_day_and_projects_six_columns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 1-day batch must return that day's rows, projected to what gold needs."""
        target = tmp_path / "events"
        write_deltalake(
            table_or_uri=str(target),
            data=_silver_frame(
                [
                    datetime(2026, 10, 6, 23, 0, 0),
                    datetime(2026, 10, 7, 0, 0, 0),
                    datetime(2026, 10, 7, 12, 0, 0),
                    datetime(2026, 10, 8, 1, 0, 0),
                ]
            ).to_arrow(),
            partition_by=["year", "month", "day", "hour"],
        )
        monkeypatch.setattr(silver_to_gold, "SILVER_GH_EVENTS", str(target))

        result: DataFrame = silver_to_gold._read_silver_events([date(2026, 10, 7)]).collect()

        assert result.columns == ["type", "action", "actor_id", "repo_id", "org_id", "created_at"]
        # row order across partitions isn't guaranteed; the gold agg sorts later
        assert sorted(result["actor_id"].to_list()) == [101, 102]

    @pytest.mark.transform
    def test_multi_day_batch_keeps_both_ends(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both ends of a multi-day batch must survive the partition predicate."""
        target = tmp_path / "events"
        write_deltalake(
            table_or_uri=str(target),
            data=_silver_frame(
                [
                    datetime(2026, 10, 5, 23, 0, 0),
                    datetime(2026, 10, 6, 12, 0, 0),
                    datetime(2026, 10, 7, 0, 0, 0),
                    datetime(2026, 10, 7, 23, 0, 0),
                    datetime(2026, 10, 8, 1, 0, 0),
                ]
            ).to_arrow(),
            partition_by=["year", "month", "day", "hour"],
        )
        monkeypatch.setattr(silver_to_gold, "SILVER_GH_EVENTS", str(target))

        result: DataFrame = silver_to_gold._read_silver_events(
            [date(2026, 10, 6), date(2026, 10, 7)]
        ).collect()

        assert sorted(result["actor_id"].to_list()) == [101, 102, 103]
