"""Tests for Gold layer transformations (silver_to_gold.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest
from polars.dataframe.frame import DataFrame
from polars.lazyframe.frame import LazyFrame

from core.transforms.silver_to_gold import _build_gold_daily


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
