"""
Entrypoint: execute Prefect flows directly (no deployment).

Usage:
    uv run main.py                 # execute bronze + silver + gold (default)
    uv run main.py bronze          # execute only bronze
    uv run main.py silver          # execute only silver
    uv run main.py gold            # execute only gold

Options:
    --days N                       # days of GH Archive to ingest in bronze (default: 7)
"""

import argparse

from pipelines.bronze_flow import bronze_ingestion_flow
from pipelines.gold_flow import gold_transform_flow
from pipelines.silver_flow import silver_transform_flow

DEFAULT_DAYS: int = 7


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute Prefect flows directly (no deployment).")
    parser.add_argument(
        "flow",
        nargs="?",
        default="",
        help="bronze, silver or gold (default: all three, in order)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"days of GH Archive to ingest in bronze (default: {DEFAULT_DAYS})",
    )
    args = parser.parse_args()

    match args.flow:
        case "bronze":
            serve_bronze(days=args.days)
        case "silver":
            serve_silver()
        case "gold":
            serve_gold()
        case _:
            serve_all(days=args.days)
