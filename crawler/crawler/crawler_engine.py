"""
Async keyword crawler engine
"""

import asyncio
import csv
import json
import logging
from datetime import datetime

from crawler.crawler.job_manager import JobManager
from crawler.crawler.models import KeywordResult
from crawler.crawler.progress_tracker import ProgressTracker
from provider.core.exceptions import NoAccountAvailable
from provider.core.types import CallParams
from provider.providers.deepseek import DeepSeek

logger = logging.getLogger(__name__)


class CrawlerEngine:
    """Async keyword crawler engine"""

    def __init__(
        self,
        deepseek: DeepSeek,
        job_manager: JobManager,
        job_name: str,
        run_id: str,
        progress_tracker: ProgressTracker,
    ):
        self.deepseek = deepseek
        self.job_manager = job_manager
        self.job_name = job_name
        self.run_id = run_id
        self.progress = progress_tracker
        self.run_dir = job_manager.jobs_dir / job_name / "runs" / run_id

    async def crawl_keywords(self, keywords: list[str]) -> None:
        """Process all keywords with progress tracking"""
        processed_count = 0
        failed_count = 0

        for keyword in keywords:
            result = await self._process_keyword(keyword)

            # Save to JSONL immediately (crash recovery)
            self._save_result(result)

            # Update progress
            self.progress.update(keyword, result.success)

            # Update counters
            processed_count += 1
            if not result.success:
                failed_count += 1

            # Update metadata periodically
            if processed_count % 10 == 0:
                self.job_manager.update_run_status(
                    self.job_name,
                    self.run_id,
                    status="running",
                    processed_keywords=processed_count,
                    failed_keywords=failed_count,
                )

        # Final metadata update
        self.job_manager.update_run_status(
            self.job_name,
            self.run_id,
            status="running",
            processed_keywords=processed_count,
            failed_keywords=failed_count,
        )

    async def _process_keyword(self, keyword: str) -> KeywordResult:
        """Process a single keyword with retry on NoAccountAvailable"""
        timestamp = datetime.now().isoformat()
        retry_count = 0

        while True:
            try:
                params = CallParams(
                    messages=keyword, enable_thinking=False, enable_search=True
                )

                call_result = await self.deepseek.call(params)

                if retry_count > 0:
                    logger.info(
                        f"Successfully processed keyword '{keyword}' after {retry_count} retries"
                    )

                return KeywordResult(
                    keyword=keyword,
                    timestamp=timestamp,
                    success=True,
                    error_message=None,
                    content=call_result.content,
                    num_sources=len(call_result.sources),
                    num_rankings=len(call_result.rankings),
                    rankings=call_result.rankings,
                    sources=call_result.sources,
                )

            except NoAccountAvailable:
                retry_count += 1
                logger.warning(
                    f"No account available for keyword '{keyword}' (retry #{retry_count}). "
                    f"Waiting 1 second before retry..."
                )
                await asyncio.sleep(1)
                # Continue to next iteration of while loop

            except Exception as e:
                logger.error(
                    f"Failed to process keyword '{keyword}': {e}", exc_info=True
                )
                return KeywordResult(
                    keyword=keyword,
                    timestamp=timestamp,
                    success=False,
                    error_message=str(e),
                    content="",
                    num_sources=0,
                    num_rankings=0,
                    rankings=[],
                    sources=[],
                )

    def _save_result(self, result: KeywordResult) -> None:
        """Append result to JSONL file (one JSON object per line)"""
        jsonl_path = self.run_dir / "results.jsonl"

        with open(jsonl_path, "a", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False)
            f.write("\n")

        # Also append to CSV for easy viewing/compatibility
        csv_path = self.run_dir / "results.csv"
        file_exists = csv_path.exists()
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "keyword",
                    "timestamp",
                    "success",
                    "error_message",
                    "content",
                    "rankings",
                    "sources",
                ],
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(
                {
                    "keyword": result.keyword,
                    "timestamp": result.timestamp,
                    "success": result.success,
                    "error_message": result.error_message,
                    "content": result.content,
                    "rankings": json.dumps(result.rankings, ensure_ascii=False),
                    "sources": json.dumps(result.sources, ensure_ascii=False),
                }
            )
