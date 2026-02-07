"""
Result loader for reading crawl results (JSONL/CSV)
"""

import csv
import json
from pathlib import Path

from crawler.analyzer.models import KeywordResult


class ResultLoader:
    """Loads results from JSONL"""

    def load_run_results(self, job_name: str, run_id: str) -> list[KeywordResult]:
        """Load results from JSONL (preferred) or CSV (fallback)."""
        run_dir = Path("jobs") / job_name / "runs" / run_id
        jsonl_path = run_dir / "results.jsonl"
        csv_path = run_dir / "results.csv"

        if jsonl_path.exists():
            return self._load_jsonl(jsonl_path)

        if csv_path.exists():
            return self._load_csv(csv_path)

        raise ValueError(f"Results file not found: {jsonl_path} / {csv_path}")

    def _load_jsonl(self, path: Path) -> list[KeywordResult]:
        results: list[KeywordResult] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                results.append(
                    KeywordResult(
                        keyword=data.get("keyword", ""),
                        success=bool(data.get("success")),
                        rankings=data.get("rankings", []) or [],
                        sources=data.get("sources", []) or [],
                    )
                )
        return results

    def _load_csv(self, path: Path) -> list[KeywordResult]:
        results: list[KeywordResult] = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                keyword = row.get("keyword", "")
                success_raw = (row.get("success") or "").strip().lower()
                success = success_raw in {"1", "true", "yes", "y"}

                rankings_raw = row.get("rankings") or "[]"
                sources_raw = row.get("sources") or "[]"

                try:
                    rankings = json.loads(rankings_raw)
                except Exception:
                    rankings = []

                try:
                    sources = json.loads(sources_raw)
                except Exception:
                    sources = []

                results.append(
                    KeywordResult(
                        keyword=keyword,
                        success=success,
                        rankings=rankings or [],
                        sources=sources or [],
                    )
                )
        return results
