"""
AI Ranking Analyzer

Analyzes crawl results and generates statistics/reports.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from crawler.analyzer import ResultLoader, StatisticsCalculator, ReportGenerator


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="AI Ranking Analyzer")

    parser.add_argument("job_name", help="Job name to analyze")
    parser.add_argument(
        "--run-id", help="Specific run ID to analyze (default: latest)"
    )
    parser.add_argument(
        "--export",
        choices=["json", "html", "all"],
        default="all",
        help="Export format (default: all)",
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    # Load job metadata
    metadata_path = Path("jobs") / args.job_name / "metadata.json"
    if not metadata_path.exists():
        print(f"错误：任务 '{args.job_name}' 不存在")
        return

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Determine run to analyze
    if args.run_id:
        run_id = args.run_id
    else:
        # Use latest run
        if not metadata["runs"]:
            print(f"错误：任务 '{args.job_name}' 没有运行记录")
            return
        run_id = metadata["runs"][-1]["run_id"]

    print(f"分析任务: {args.job_name}")
    print(f"运行ID: {run_id}")

    # Load results
    loader = ResultLoader()
    try:
        results = loader.load_run_results(args.job_name, run_id)
    except ValueError as e:
        print(f"错误：{e}")
        return

    print(f"加载了 {len(results)} 个关键词结果")

    # Calculate statistics
    calculator = StatisticsCalculator()
    stats = calculator.calculate(results, metadata.get("target_product"))

    # Set metadata
    stats.job_name = args.job_name
    stats.run_id = run_id
    stats.analyzed_at = datetime.now().isoformat()

    # Generate reports
    run_dir = Path("jobs") / args.job_name / "runs" / run_id
    generator = ReportGenerator(stats, run_dir)

    if args.export in ["json", "all"]:
        generator.save_json()
        print("✓ 已生成 statistics.json")

    if args.export in ["html", "all"]:
        generator.save_html()
        print("✓ 已生成 report.html")

    # Display summary
    print(generator.generate_console_summary())


if __name__ == "__main__":
    main()
