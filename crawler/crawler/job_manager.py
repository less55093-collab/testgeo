"""
Job lifecycle and persistence management
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from crawler.crawler.models import JobMetadata, RunMetadata

logger = logging.getLogger(__name__)


class JobManager:
    """Manages job lifecycle and persistence"""

    def __init__(self, jobs_dir: Path = Path("jobs")):
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(exist_ok=True)

    def create_job(
        self, job_name: str, keywords: list[str], target_product: str | None = None
    ) -> JobMetadata:
        """Create new job with metadata"""
        job_dir = self.jobs_dir / job_name
        if job_dir.exists():
            raise ValueError(f"Job '{job_name}' already exists")

        job_dir.mkdir(parents=True)

        metadata = JobMetadata(
            job_name=job_name,
            created_at=datetime.now().isoformat(),
            keywords=keywords,
            target_product=target_product,
            total_keywords=len(keywords),
            runs=[],
        )

        self._save_metadata(job_name, metadata)
        logger.info(f"Created job '{job_name}' with {len(keywords)} keywords")

        return metadata

    def load_job(self, job_name: str) -> JobMetadata:
        """Load existing job metadata"""
        metadata_path = self.jobs_dir / job_name / "metadata.json"
        if not metadata_path.exists():
            raise ValueError(f"Job '{job_name}' not found")

        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return JobMetadata(**data)

    def start_run(self, job_name: str) -> str:
        """Create new run folder and update metadata"""
        metadata = self.load_job(job_name)

        # Generate run ID
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create run directory
        run_dir = self.jobs_dir / job_name / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create run metadata
        run_meta = RunMetadata(
            run_id=run_id, started_at=datetime.now().isoformat(), status="running"
        )

        # Update job metadata
        metadata.runs.append(asdict(run_meta))
        self._save_metadata(job_name, metadata)

        logger.info(f"Started run '{run_id}' for job '{job_name}'")

        return run_id

    def update_run_status(
        self, job_name: str, run_id: str, status: str, **kwargs
    ) -> None:
        """Update run status and other fields"""
        metadata = self.load_job(job_name)

        # Find and update run
        for run in metadata.runs:
            if run["run_id"] == run_id:
                run["status"] = status
                if status in ["completed", "failed"]:
                    run["completed_at"] = datetime.now().isoformat()
                for key, value in kwargs.items():
                    run[key] = value
                break

        self._save_metadata(job_name, metadata)
        logger.info(f"Updated run '{run_id}' status to '{status}'")

    def save_keyword_result(
        self,
        job_name: str,
        run_id: str,
        keyword: str,
        success: bool,
        content: str = "",
        rankings: list = None,
        sources: list = None,
        error: str = None,
    ) -> None:
        """Save keyword processing result to JSONL"""
        if rankings is None:
            rankings = []
        if sources is None:
            sources = []

        run_dir = self.jobs_dir / job_name / "runs" / run_id
        jsonl_path = run_dir / "results.jsonl"

        result = {
            "keyword": keyword,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "error_message": error,
            "content": content,
            "num_sources": len(sources),
            "num_rankings": len(rankings),
            "rankings": rankings,
            "sources": sources,
        }

        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    def get_unprocessed_keywords(self, job_name: str, run_id: str) -> list[str]:
        """Get keywords not yet processed in JSONL"""
        metadata = self.load_job(job_name)
        run_dir = self.jobs_dir / job_name / "runs" / run_id
        jsonl_path = run_dir / "results.jsonl"

        if not jsonl_path.exists():
            return metadata.keywords

        # Read processed keywords from JSONL
        processed = set()
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    processed.add(result["keyword"])

        # Return unprocessed
        return [kw for kw in metadata.keywords if kw not in processed]

    def _save_metadata(self, job_name: str, metadata: JobMetadata) -> None:
        """Save metadata to file"""
        metadata_path = self.jobs_dir / job_name / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(asdict(metadata), f, indent=2, ensure_ascii=False)
