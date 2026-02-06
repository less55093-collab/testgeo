"""
AI Ranking Crawler

Fetches ranking data from AI platforms for keyword analysis.
"""

import argparse
import asyncio
import logging
from pathlib import Path

from crawler.crawler import (
    CrawlerEngine,
    JobManager,
    ProgressTracker,
    setup_logging,
)
from provider.providers.deepseek import DeepSeek

# Setup logger
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="AI Platform Ranking Crawler")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # New job
    new_parser = subparsers.add_parser("new", help="Create new job")
    new_parser.add_argument("job_name", help="Unique job name")
    new_parser.add_argument(
        "--keywords", nargs="+", required=True, help="Keywords to crawl"
    )
    new_parser.add_argument(
        "--target-product", help="Your product name for tracking (optional)"
    )
    new_parser.add_argument("--config", default="config.json", help="Config file path")

    # Resume job
    resume_parser = subparsers.add_parser("resume", help="Resume existing job")
    resume_parser.add_argument("job_name", help="Job name to resume")
    resume_parser.add_argument(
        "--config", default="config.json", help="Config file path"
    )

    # Rerun job
    rerun_parser = subparsers.add_parser("rerun", help="Re-run existing job")
    rerun_parser.add_argument("job_name", help="Job name to re-run")
    rerun_parser.add_argument(
        "--config", default="config.json", help="Config file path"
    )

    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_args()

    job_manager = JobManager()

    # Determine operation mode
    if args.command == "new":
        # Create new job
        metadata = job_manager.create_job(
            args.job_name, args.keywords, args.target_product
        )
        run_id = job_manager.start_run(args.job_name)
        keywords_to_process = args.keywords

    elif args.command == "resume":
        # Resume existing job
        metadata = job_manager.load_job(args.job_name)
        if not metadata.runs:
            raise ValueError(f"Job '{args.job_name}' has no runs")

        current_run = metadata.runs[-1]
        if current_run["status"] == "completed":
            raise ValueError(
                f"Job '{args.job_name}' already completed. Use 'rerun' to run again."
            )

        run_id = current_run["run_id"]
        keywords_to_process = job_manager.get_unprocessed_keywords(
            args.job_name, run_id
        )

        if not keywords_to_process:
            print(f"All keywords already processed for job '{args.job_name}'")
            return

    elif args.command == "rerun":
        # Re-run with existing metadata
        metadata = job_manager.load_job(args.job_name)
        run_id = job_manager.start_run(args.job_name)
        keywords_to_process = metadata.keywords

    else:
        raise ValueError(f"Unknown command: {args.command}")

    # Setup logging
    run_dir = Path("jobs") / args.job_name / "runs" / run_id
    log_file = run_dir / "crawler.log"
    setup_logging(log_file)

    logger.info(f"Starting crawler for job '{args.job_name}', run '{run_id}'")
    logger.info(f"Keywords to process: {len(keywords_to_process)}")

    # Initialize DeepSeek
    deepseek = DeepSeek(args.config)

    # Setup progress tracker
    progress = ProgressTracker(args.job_name)

    # Create crawler
    crawler = CrawlerEngine(deepseek, job_manager, args.job_name, run_id, progress)

    # Run crawl with progress display
    try:
        with progress.progress:
            progress.start(len(keywords_to_process))
            await crawler.crawl_keywords(keywords_to_process)

        # Mark as completed
        job_manager.update_run_status(args.job_name, run_id, status="completed")

        # Show summary
        progress.show_completion_summary()
        print(f"\nResults saved to: {run_dir}")

    except KeyboardInterrupt:
        logger.info("Crawl interrupted by user")
        job_manager.update_run_status(args.job_name, run_id, status="paused")
        print("\n[yellow]Crawl paused. Resume with 'resume' command[/yellow]")

    except Exception as e:
        logger.error(f"Crawl failed: {e}", exc_info=True)
        job_manager.update_run_status(args.job_name, run_id, status="failed")
        print(f"\n[red]Crawl failed: {e}[/red]")
        raise


if __name__ == "__main__":
    asyncio.run(main())
