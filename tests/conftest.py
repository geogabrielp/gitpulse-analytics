"""Shared fixtures for all GitPulse Analytics tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import polars as pl
import pytest
from moto import mock_aws
from s3fs.core import S3FileSystem

from core.config import settings
from core.helpers.s3 import get_s3_fs


@pytest.fixture
def mock_minio() -> Generator[None, None, None]:
    """
    Replace MinIO with an in-memory S3 mock (moto).

    Creates the three medallion buckets before each test
    and cleans up automatically when the test finishes.
    """
    with mock_aws():
        fs: S3FileSystem = get_s3_fs()
        fs.mkdir(settings.minio.bucket_bronze)
        fs.mkdir(settings.minio.bucket_silver)
        fs.mkdir(settings.minio.bucket_gold)
        yield


@pytest.fixture
def sample_bronze_df() -> pl.DataFrame:
    """
    Minimal valid bronze DataFrame matching BRONZE_EVENTS_SCHEMA.

    Contains 3 events of known types (PushEvent, WatchEvent, IssuesEvent)
    plus one row with an org and one without.
    """
    return pl.DataFrame(
        data={
            "id": ["1", "2", "3"],
            "type": ["PushEvent", "WatchEvent", "IssuesEvent"],
            "actor": [
                '{"id":100,"login":"user1","display_login":"User One","gravatar_id":"","url":"https://api.github.com/users/user1","avatar_url":"https://avatars.com/u/100"}',
                '{"id":200,"login":"user2","display_login":"User Two","gravatar_id":"","url":"https://api.github.com/users/user2","avatar_url":"https://avatars.com/u/200"}',
                '{"id":300,"login":"bot[bot]","display_login":"Bot","gravatar_id":"","url":"https://api.github.com/users/bot","avatar_url":"https://avatars.com/u/300"}',
            ],
            "repo": [
                '{"id":10,"name":"org/repo1","url":"https://api.github.com/repos/org/repo1"}',
                '{"id":20,"name":"org/repo2","url":"https://api.github.com/repos/org/repo2"}',
                '{"id":30,"name":"org/repo3","url":"https://api.github.com/repos/org/repo3"}',
            ],
            "payload": [
                '{"push_id":1,"size":1}',
                '{"action":"starred"}',
                '{"action":"opened"}',
            ],
            "public": [True, True, True],
            "created_at": [
                "2026-07-19T10:00:00Z",
                "2026-07-19T11:00:00Z",
                "2026-07-19T12:00:00Z",
            ],
            "org": [
                '{"id":1,"login":"org1","gravatar_id":"","url":"https://api.github.com/orgs/org1","avatar_url":"https://avatars.com/orgs/1"}',
                '{"id":2,"login":"org2","gravatar_id":"","url":"https://api.github.com/orgs/org2","avatar_url":"https://avatars.com/orgs/2"}',
                None,
            ],
        },
        schema={
            "id": pl.String,
            "type": pl.String,
            "actor": pl.String,
            "repo": pl.String,
            "payload": pl.String,
            "public": pl.Boolean,
            "created_at": pl.String,
            "org": pl.String,
        },
    )


@pytest.fixture
def sample_silver_events_df() -> pl.DataFrame:
    """A valid Silver events DataFrame for contract and transform tests."""
    return pl.DataFrame(
        data={
            "id": [1001, 1002, 1003],
            "type": [
                "PushEvent",
                "PullRequestEvent",
                "IssuesEvent",
            ],
            "action": [
                "pushed",
                "opened",
                "closed",
            ],
            "actor_id": [101, 202, 303],
            "repo_id": [10, 20, 30],
            "org_id": [1, 2, None],
            "public": [True, True, False],
            "created_at": [
                datetime(year=2026, month=7, day=19, hour=10, minute=0, second=0, tzinfo=UTC),
                datetime(year=2026, month=7, day=19, hour=11, minute=0, second=0, tzinfo=UTC),
                datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0, tzinfo=UTC),
            ],
            "year": ["2026", "2026", "2026"],
            "month": ["07", "07", "07"],
            "day": ["19", "19", "19"],
            "hour": ["10", "11", "12"],
        }
    )


@pytest.fixture
def sample_gold_daily_df() -> pl.DataFrame:
    """A valid Gold daily aggregation row for contract tests."""
    return pl.DataFrame(
        data={
            "day": [datetime(year=2026, month=7, day=19).date()],
            "repo_id": [10],
            "org_id": [1],
            "total_events": [10],
            "unique_actors": [5],
            "push_events": [4],
            "pr_events": [2],
            "issue_events": [2],
            "watch_events": [1],
            "fork_events": [1],
            "release_events": [0],
            "comment_events": [0],
            "review_events": [0],
            "prs_opened": [1],
            "prs_merged": [1],
            "prs_closed_unmerged": [0],
            "pr_merge_rate": [1.0],
            "issues_opened": [1],
            "issues_closed": [1],
            "issue_close_rate": [0.5],
            "gitpulse_score": [25.0],
            "updated_at": [datetime(year=2026, month=7, day=19, hour=12, minute=0, second=0)],
            "year": ["2026"],
            "month": ["07"],
        }
    )
