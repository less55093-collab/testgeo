"""
Result loader for reading JSONL data
"""

import json
from pathlib import Path

from crawler.analyzer.models import KeywordResult


class ResultLoader:
    """Loads results from JSONL"""

    def load_run_results(self, job_name: str, run_id: str) -> list[KeywordResult]:
        """Load results from JSONL"""
        jsonl_path = Path("jobs") / job_name / "runs" / run_id / "results.jsonl"

        if not jsonl_path.exists():
            raise ValueError(f"Results file not found: {jsonl_path}")

        results = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    results.append(
                        KeywordResult(
                            keyword=data["keyword"],
                            success=data["success"],
                            rankings=data.get("rankings", []),
                            sources=data.get("sources", []),
                        )
                    )

        return results
