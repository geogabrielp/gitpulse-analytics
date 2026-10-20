"""
Entrypoint: execute Prefect flows directly or serve them on a schedule.

Usage:
    uv run main.py                 # execute bronze + silver + gold (default)
    uv run main.py bronze          # execute only bronze
    uv run main.py silver          # execute only silver
    uv run main.py gold            # execute only gold
    uv run main.py serve           # serve the hourly pipeline (long-running process)

Options:
    --days N                       # days of GH Archive to ingest in bronze
                                   # (default: 7 or 1 when serving)
"""

import argparse

from prefect.schedules import Cron

from pipelines.bronze_flow import bronze_ingestion_flow
from pipelines.gold_flow import gold_transform_flow
from pipelines.hourly_flow import hourly_pipeline_flow
from pipelines.silver_flow import silver_transform_flow

DEFAULT_DAYS: int = 7
DEFAULT_SERVE_DAYS: int = 1

# GH Archive can publish an hour late, trigger at :35 to leave a safety margin.
_HOURLY_CRON: str = "35 * * * *"


def serve_all(days: int = DEFAULT_DAYS) -> None:
    """Execute bronze, silver, and gold flows sequentially."""
    bronze_ingestion_flow(days=days)
    silver_transform_flow(batch_size=12)
    gold_transform_flow(batch_size_days=2)


def serve_bronze(days: int = DEFAULT_DAYS) -> None:
    """Execute only the bronze ingestion flow."""
    bronze_ingestion_flow(days=days)


def serve_silver() -> None:
    """Execute only the silver transformation flow."""
    silver_transform_flow(batch_size=24)


def serve_gold() -> None:
    """Execute only the gold transformation flow."""
    gold_transform_flow(batch_size_days=2)


def serve_hourly(days: int = DEFAULT_SERVE_DAYS) -> None:
    """
    Serve the hourly pipeline, one run at minute 35 of every hour (UTC).

    The process must stay alive to pick up scheduled runs. Without it the
    deployment remains registered but runs are not executed.
    """
    hourly_pipeline_flow.serve(
        name="gitpulse-hourly",
        schedules=[
            Cron(
                _HOURLY_CRON,
                timezone="UTC",
                slug="hourly",
                parameters={"days": days},
            )
        ],
        limit=1,
        pause_on_shutdown=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Execute Prefect flows directly or serve the hourly pipeline."
    )
    parser.add_argument(
        "flow",
        nargs="?",
        default="",
        help="bronze, silver, gold or serve (default: all three, in order)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"days of GH Archive to ingest in bronze (default: {DEFAULT_DAYS}, or 1 when serving)",
    )
    args = parser.parse_args()

    match args.flow:
        case "bronze":
            serve_bronze(days=args.days or DEFAULT_DAYS)
        case "silver":
            serve_silver()
        case "gold":
            serve_gold()
        case "serve":
            serve_hourly(days=args.days or DEFAULT_SERVE_DAYS)
        case _:
            serve_all(days=args.days or DEFAULT_DAYS)
