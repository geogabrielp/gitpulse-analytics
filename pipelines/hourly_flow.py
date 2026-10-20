"""
Hourly orchestration flow: bronze → silver → gold in a single scheduled run.
"""

from prefect import flow

from pipelines.bronze_flow import bronze_ingestion_flow
from pipelines.gold_flow import gold_transform_flow
from pipelines.silver_flow import silver_transform_flow


@flow(name="hourly-pipeline", log_prints=True)
def hourly_pipeline_flow(days: int = 1) -> None:
    """
    Run the full pipeline over a rolling window of GH Archive hours.

    Args:
        days: Bronze lookback window (default 1). Re-checking the last day on
            every run makes ingestion self-healing: hours that were delayed on
            GH Archive or missed while nothing was running are picked up later.
    """
    bronze_ingestion_flow(days=days)
    silver_transform_flow(batch_size=12)
    gold_transform_flow(batch_size_days=2)


__all__: list[str] = ["hourly_pipeline_flow"]
