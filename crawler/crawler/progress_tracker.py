"""
Rich-based progress tracking
"""

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table


class ProgressTracker:
    """Rich-based progress tracker"""

    def __init__(self, job_name: str):
        self.console = Console()
        self.job_name = job_name
        self.success_count = 0
        self.failure_count = 0

        # Create progress bar
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=self.console,
        )

        self.task_id = None

    def start(self, total: int):
        """Initialize progress bar"""
        self.task_id = self.progress.add_task(
            f"Crawling keywords for job '{self.job_name}'", total=total
        )

    def update(self, keyword: str, success: bool):
        """Update progress after processing a keyword"""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        if self.task_id is None:
            raise RuntimeError("ProgressTracker not started. Call start() first.")
        self.progress.update(self.task_id, advance=1)

    def show_completion_summary(self):
        """Show summary after completion"""
        table = Table(title="Crawl Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Job Name", self.job_name)
        table.add_row("Total Processed", str(self.success_count + self.failure_count))
        table.add_row("Successful", str(self.success_count))
        table.add_row("Failed", str(self.failure_count))

        if self.success_count + self.failure_count > 0:
            success_rate = (
                self.success_count / (self.success_count + self.failure_count) * 100
            )
            table.add_row("Success Rate", f"{success_rate:.1f}%")

        self.console.print(table)
