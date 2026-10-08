from datetime import date
from time import perf_counter

from prefect import flow, task

from core.helpers.logger import get_logger, green, red, yellow
from core.transforms.silver_to_gold import (
    TransformResult,
    resolve_pending_days,
    silver_to_gold,
)


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def resolve_task() -> list[date]:
    """Discover pending days from the gold daily watermark."""
    return resolve_pending_days()


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def transform_task(batch: list[date]) -> TransformResult:
    """Process one batch of days through the Silver -> Gold pipeline."""
    return silver_to_gold(days_batch=batch)


@flow(name="gold-transform", log_prints=True)
def gold_transform_flow(batch_size_days: int = 7) -> None:
    """
    Aggregate pending Silver events into the single ``gold_daily`` table.

    Single scan → single aggregate (event types, PR actions, issue actions,
    GitPulse Score) → Pandera validate → idempotent day-replacing write.

    Args:
        batch_size_days: Number of days per batch (default 7).
    """
    logger = get_logger(__name__)
    pending: list[date] = resolve_task()

    batches: list[list[date]] = [
        pending[i : i + batch_size_days] for i in range(0, len(pending), batch_size_days)
    ]

    failed: int = 0
    succeeded: int = 0
    total: int = len(batches)
    timer_start: float = perf_counter()

    for i, batch in enumerate(batches, start=1):
        logger.info(
            "processing batch %s/%s: %d days (%s → %s)",
            yellow(i),
            yellow(total),
            len(batch),
            batch[0],
            batch[-1],
        )

        result: TransformResult = transform_task(batch=batch)

        if result is TransformResult.SUCCESS:
            logger.info("batch completed!")
            succeeded += 1
        else:
            logger.error("batch failed!")
            failed += 1

    timer_end: float = perf_counter()

    logger.info(
        "%s batches succeeded • %s batches failed",
        green(succeeded),
        red(failed),
    )
    logger.info(
        "total time taken: %s seconds",
        yellow(f"{timer_end - timer_start:.2f}"),
    )
    logger.info("Gold transform completed, check at http://localhost:9001/browser/gold/")


__all__: list[str] = ["gold_transform_flow"]
