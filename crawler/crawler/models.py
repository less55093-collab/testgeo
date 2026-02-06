"""
Data models for crawler
"""

from dataclasses import dataclass


@dataclass
class RunMetadata:
    """Metadata for a single run"""

    run_id: str
    started_at: str
    completed_at: str | None = None
    status: str = "running"  # "running" | "completed" | "paused" | "failed"
    processed_keywords: int = 0
    failed_keywords: int = 0


@dataclass
class JobMetadata:
    """Metadata for a job"""

    job_name: str
    created_at: str
    keywords: list[str]
    target_product: str | None
    total_keywords: int
    runs: list[dict]


@dataclass
class KeywordResult:
    """Result from processing a single keyword"""

    keyword: str
    timestamp: str
    success: bool
    error_message: str | None
    content: str
    num_sources: int
    num_rankings: int
    rankings: list[dict]
    sources: list[dict]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "keyword": self.keyword,
            "timestamp": self.timestamp,
            "success": self.success,
            "error_message": self.error_message,
            "content": self.content,
            "num_sources": self.num_sources,
            "num_rankings": self.num_rankings,
            "rankings": self.rankings,
            "sources": self.sources,
        }
