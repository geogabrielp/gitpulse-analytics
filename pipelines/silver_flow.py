from time import perf_counter

from prefect import flow, task

from core.helpers.logger import get_logger, green, red, yellow
from core.helpers.s3 import get_s3_fs
from core.transforms.bronze_to_silver import (
    TransformResult,
    resolve_pending_partitions,
    transform_batch,
)


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def resolve_task() -> list[str]:
    """Discover pending Bronze partitions."""
    return resolve_pending_partitions(fs=get_s3_fs())


@task(retries=3, retry_delay_seconds=30, log_prints=True)
def transform_task(batch: list[str]) -> TransformResult:
    """Process one batch through the Bronze -> Silver pipeline."""
    return transform_batch(batch_paths=batch)


@flow(name="silver-transform", log_prints=True)
def silver_transform_flow(batch_size: int = 12) -> None:
    """
    Transform pending Bronze partitions into Silver Delta tables.

    Args:
        batch_size: Max partitions per batch (default 12).
    """
    logger = get_logger(__name__)
    pending: list[str] = resolve_task()

    batches: list[list[str]] = [
        pending[i : i + batch_size] for i in range(0, len(pending), batch_size)
    ]

    failed: int = 0
    succeeded: int = 0
    total: int = len(batches)
    timer_start: float = perf_counter()

    for i, batch in enumerate(batches, start=1):
        logger.info(
            "processing batch %s/%s: %d partitions",
            yellow(i),
            yellow(total),
            len(batch),
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
    logger.info("Transform completed, check at http://localhost:9011/browser/silver/")
