from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from logging import Logger, LoggerAdapter

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from core.helpers.logger import get_logger, green, magenta, red, yellow
from core.ingestion.bronze import IngestResult, generate_hourly_datetimes, ingest_hour


def create_progress_bar(total: int) -> tuple[Progress, TaskID]:
    """
    Build a rich progress bar to track ingestion workers.
    """
    progress = Progress(
        SpinnerColumn(spinner_name="simpleDotsScrolling", style="bold green", speed=1.0),
        TextColumn("[magenta] {task.description}"),
        BarColumn(bar_width=100, style="dim", complete_style="green"),
        TextColumn("[bold green]{task.percentage:>6.1f}%"),
        TextColumn("•"),
        TimeElapsedColumn(),
    )
    task_id: TaskID = progress.add_task(description="starting...", total=total)
    return progress, task_id


def run_ingestion(days: int, max_workers: int) -> None:
    """
    Ingest GH Archive data for the past N days using a thread pool.

    Each hour is ingested by a worker thread. Results are collected as they complete
    and reported as a summary — succeeded, skipped (already in lake or not yet
    published), and failed.
    """
    logger: Logger | LoggerAdapter[Logger] = get_logger(__name__)

    hours_to_ingest: list[datetime] = generate_hourly_datetimes(days=days)
    total_hours_to_ingest: int = len(hours_to_ingest)

    logger.info(
        "Starting ingestion: days=%s hours=%s workers=%s",
        magenta(days),
        magenta(total_hours_to_ingest),
        magenta(max_workers),
    )

    progress, task_id = create_progress_bar(total=total_hours_to_ingest)

    def worker(hour: datetime) -> IngestResult:
        """Ingest a single hour and update the progress bar."""
        file_label: str = f"{hour.year}-{hour.month:02d}-{hour.day:02d}-{hour.hour:02d}.json.gz"

        try:
            result: IngestResult = ingest_hour(dt=hour)
        except Exception as ex:
            progress.console.log(
                # log only the first 200 chars of the error for brevity
                f"file [cyan]{file_label}[/cyan] [red]failed[/red]: {str(ex)[:100]}"
            )
            progress.update(task_id, advance=1, description=file_label)
            return IngestResult.FAILED

        progress.update(task_id, advance=1, description=file_label)
        return result

    # counters for metrics
    failed: int = 0
    skipped: int = 0
    succeeded: int = 0

    with progress, ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[IngestResult], datetime] = {
            executor.submit(worker, hour): hour for hour in hours_to_ingest
        }
        # process results as they complete, not in submission order
        for future in as_completed(futures):
            try:
                # collect succeeded/skipped/failed metrics
                match future.result():
                    case IngestResult.SUCCESS:
                        succeeded += 1
                    case IngestResult.SKIPPED:
                        skipped += 1
                    case IngestResult.FAILED:
                        failed += 1
            except Exception as exc:
                # catch unexpected exceptions so a single worker failure
                # doesn't crash the entire ingestion loop
                progress.console.log(
                    f"worker [red]failed[/red] with unexpected exception: {str(exc)[:100]}"
                )
                progress.update(task_id, advance=1, description="error")
                failed += 1

    logger.info(
        "%s ingested • %s skipped (already ingested or not yet available) • %s failed",
        green(succeeded),
        yellow(skipped),
        red(failed),
    )
    logger.info("Ingestion completed, check at http://localhost:9011/browser/bronze/")
