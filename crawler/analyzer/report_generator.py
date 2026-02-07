"""
Report generator for statistics
"""

import csv
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from crawler.analyzer.models import OverallStatistics

# Path to HTML template
TEMPLATE_PATH = Path(__file__).parent.parent.parent / "assets" / "report_template.html"


class ReportGenerator:
    """Generates reports in various formats"""

    def __init__(self, stats: OverallStatistics, run_dir: Path):
        self.stats = stats
        self.run_dir = run_dir
        self._raw_results = None  # Lazy load raw results

    def save_json(self) -> None:
        """Save statistics as JSON"""
        json_path = self.run_dir / "statistics.json"

        # Convert tuple keys to strings for JSON serialization
        stats_dict = self._serialize_stats(asdict(self.stats))

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(stats_dict, f, indent=2, ensure_ascii=False)

    def save_html(self) -> None:
        """Generate Chinese HTML report"""
        html = self.generate_html_report()
        html_path = self.run_dir / "report.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    def save_text(self) -> None:
        """Generate Chinese text report"""
        report = self.generate_text_report()
        txt_path = self.run_dir / "report.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(report)

    def generate_text_report(self) -> str:
        """Generate Chinese text report (report.txt)"""
        s = self.stats

        lines: list[str] = []
        sep = "=" * 52
        sub_sep = "-" * 52

        lines.append(sep)
        lines.append(f"AI排名分析报告：{s.job_name}")
        lines.append(sep)
        lines.append(f"生成时间：{s.analyzed_at}")
        lines.append(f"运行ID：{s.run_id}")
        lines.append("")

        # Overview
        success_rate = (
            (s.successful_queries / s.total_keywords * 100)
            if s.total_keywords > 0
            else 0.0
        )
        lines.append("总览")
        lines.append(sub_sep)
        lines.append(f"总关键词数：       {s.total_keywords}")
        lines.append(f"成功查询数：       {s.successful_queries}")
        lines.append(f"失败查询数：       {s.failed_keywords}")
        lines.append(f"成功率：           {success_rate:.1f}%")
        lines.append("")

        # Sources
        lines.extend(
            self._format_source_section(
                title="排名第一的来源网站",
                sources_dict=s.source_stats.rank1_sources,
                percentage_dict=s.source_stats.rank1_source_percentage,
            )
        )
        lines.append("")
        lines.extend(
            self._format_source_section(
                title="前二名的来源网站",
                sources_dict=s.source_stats.top2_sources,
                percentage_dict=s.source_stats.top2_source_percentage,
            )
        )
        lines.append("")
        lines.extend(
            self._format_source_section(
                title="前三名的来源网站",
                sources_dict=s.source_stats.top3_sources,
                percentage_dict=s.source_stats.top3_source_percentage,
            )
        )
        lines.append("")
        lines.extend(
            self._format_source_section(
                title="所有来源网站（出现频率）",
                sources_dict=s.source_stats.source_appearances,
                percentage_dict=s.source_stats.all_source_percentage,
                max_rows=30,
            )
        )
        lines.append("")

        # Products
        lines.extend(
            self._format_product_section(
                title="排名第一的产品/平台",
                products_dict=s.product_stats.rank1_products,
                percentage_dict=s.product_stats.rank1_product_percentage,
            )
        )
        lines.append("")
        lines.extend(
            self._format_product_section(
                title="前二名的产品/平台",
                products_dict=s.product_stats.top2_products,
                percentage_dict=s.product_stats.top2_product_percentage,
            )
        )
        lines.append("")
        lines.extend(
            self._format_product_section(
                title="前三名的产品/平台",
                products_dict=s.product_stats.top3_products,
                percentage_dict=s.product_stats.top3_product_percentage,
            )
        )
        lines.append("")
        lines.extend(
            self._format_product_section(
                title="所有产品/平台（出现频率）",
                products_dict=s.product_stats.product_appearances,
                percentage_dict=s.product_stats.all_product_percentage,
                max_rows=30,
            )
        )

        # Target product
        if s.target_product_stats:
            t = s.target_product_stats
            lines.append("")
            lines.append("目标产品表现")
            lines.append(sub_sep)
            lines.append(f"目标产品：         {t.target_name}")
            lines.append(
                f"展现：             {t.total_appearances} ({t.appearance_rate:.1f}%)"
            )
            lines.append(f"排名第一：         {t.rank1_count} 次")
            lines.append(f"前二名：           {t.top2_count} 次")
            lines.append(f"前三名：           {t.top3_count} 次")
            lines.append(f"平均排名：         {t.average_rank:.2f}")

            if t.rank_position_counts:
                lines.append("")
                lines.append("各排名位置次数")
                lines.append(sub_sep)
                for rank, count in sorted(t.rank_position_counts.items()):
                    lines.append(f"第{rank}名：           {count} 次")

            lines.append("")
            lines.append("表现最好的关键词（Top 5）")
            lines.append(sub_sep)
            for keyword, rank in t.best_keywords:
                lines.append(f"{keyword}  (第{rank}名)")

            lines.append("")
            lines.append("表现最差的关键词（Top 5）")
            lines.append(sub_sep)
            for keyword, rank in t.worst_keywords:
                lines.append(f"{keyword}  (第{rank}名)")

        # Footer with averages
        lines.append("")
        lines.append("其他指标")
        lines.append(sub_sep)
        lines.append(f"平均来源数/关键词： {s.average_sources_per_keyword:.2f}")
        lines.append(f"平均排名数/关键词： {s.average_rankings_per_keyword:.2f}")

        return "\n".join(lines).rstrip() + "\n"

    def generate_html_report(self) -> str:
        """Generate Chinese HTML report with charts using template"""
        # Read template file
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            template = f.read()

        # Prepare data for template
        report_data = self._prepare_report_data()

        # Replace placeholder with JSON data
        data_json = json.dumps(report_data, ensure_ascii=False, indent=2)
        html = template.replace("/*DATA_PLACEHOLDER*/", data_json)

        return html

    def _prepare_report_data(self) -> dict:
        """Prepare all data needed for the HTML report"""
        s = self.stats

        # Prepare source chart data (rank 1, top 2, top 3)
        source_rank1_chart = self._prepare_source_rank_chart_data(1)
        source_top2_chart = self._prepare_source_rank_chart_data(2)
        source_top3_chart = self._prepare_source_rank_chart_data(3)

        # Prepare product chart data (rank 1, top 2, top 3)
        product_rank1_chart = self._prepare_product_rank_chart_data(1)
        product_top2_chart = self._prepare_product_rank_chart_data(2)
        product_top3_chart = self._prepare_product_rank_chart_data(3)

        # Prepare "all" analysis data
        all_cited_sources_data = self._prepare_all_cited_sources_data()
        all_search_sources_data = self._prepare_all_search_sources_data()
        all_products_data = self._prepare_all_products_data()

        # Prepare source/product table data
        sources_rank1_table = self._prepare_sources_rank_table_data(1)
        sources_top2_table = self._prepare_sources_rank_table_data(2)
        sources_top3_table = self._prepare_sources_rank_table_data(3)

        products_rank1_table = self._prepare_products_rank_table_data(1)
        products_top2_table = self._prepare_products_rank_table_data(2)
        products_top3_table = self._prepare_products_rank_table_data(3)

        # Prepare target product data if exists
        target_product = None
        target_product_sources = None
        target_product_raw_data = None
        if s.target_product_stats:
            target_product = self._prepare_target_product_data()
            target_product_sources = self._prepare_target_product_sources()
            target_product_raw_data = self._prepare_target_product_raw_data()

        # Prepare all keywords raw data
        all_keywords_raw_data = self._prepare_all_keywords_raw_data()

        return {
            "job_name": s.job_name,
            "run_id": s.run_id,
            "analyzed_at": s.analyzed_at,
            "total_keywords": s.total_keywords,
            "successful_queries": s.successful_queries,
            "failed_keywords": s.failed_keywords,
            "source_rank1_chart": source_rank1_chart,
            "source_top2_chart": source_top2_chart,
            "source_top3_chart": source_top3_chart,
            "all_cited_sources_chart": all_cited_sources_data["chart"],
            "all_cited_sources_table": all_cited_sources_data["table"],
            "all_search_sources_chart": all_search_sources_data["chart"],
            "all_search_sources_table": all_search_sources_data["table"],
            "product_rank1_chart": product_rank1_chart,
            "product_top2_chart": product_top2_chart,
            "product_top3_chart": product_top3_chart,
            "all_products_chart": all_products_data["chart"],
            "all_products_table": all_products_data["table"],
            "sources_rank1_table": sources_rank1_table,
            "sources_top2_table": sources_top2_table,
            "sources_top3_table": sources_top3_table,
            "products_rank1_table": products_rank1_table,
            "products_top2_table": products_top2_table,
            "products_top3_table": products_top3_table,
            "target_product": target_product,
            "target_product_sources": target_product_sources,
            "target_product_raw_data": target_product_raw_data,
            "all_keywords_raw_data": all_keywords_raw_data,
        }

    def _prepare_source_rank_chart_data(self, rank_level: int) -> dict:
        """Prepare data for source chart by rank level (1=rank1, 2=top2, 3=top3)"""
        if rank_level == 1:
            sources_dict = self.stats.source_stats.rank1_sources
        elif rank_level == 2:
            sources_dict = self.stats.source_stats.top2_sources
        else:
            sources_dict = self.stats.source_stats.top3_sources

        sorted_sources = sorted(
            sources_dict.items(), key=lambda x: x[1], reverse=True
        )[:10]

        labels = []
        data = []
        for (domain, site_name), count in sorted_sources:
            label = f"{site_name} ({domain})" if site_name != domain else domain
            labels.append(label)
            data.append(count)

        return {"labels": labels, "data": data}

    def _prepare_product_rank_chart_data(self, rank_level: int) -> dict:
        """Prepare data for product chart by rank level"""
        if rank_level == 1:
            products_dict = self.stats.product_stats.rank1_products
        elif rank_level == 2:
            products_dict = self.stats.product_stats.top2_products
        else:
            products_dict = self.stats.product_stats.top3_products

        sorted_products = sorted(
            products_dict.items(), key=lambda x: x[1], reverse=True
        )[:10]

        labels = [p for p, _ in sorted_products]
        data = [c for _, c in sorted_products]

        return {"labels": labels, "data": data}

    def _prepare_sources_rank_table_data(self, rank_level: int) -> list[dict]:
        """Prepare sources table data by rank level"""
        if rank_level == 1:
            sources_dict = self.stats.source_stats.rank1_sources
            percentage_dict = self.stats.source_stats.rank1_source_percentage
        elif rank_level == 2:
            sources_dict = self.stats.source_stats.top2_sources
            percentage_dict = self.stats.source_stats.top2_source_percentage
        else:
            sources_dict = self.stats.source_stats.top3_sources
            percentage_dict = self.stats.source_stats.top3_source_percentage

        sorted_sources = sorted(
            percentage_dict.items(), key=lambda x: x[1], reverse=True
        )[:20]

        rows = []
        for (domain, site_name), percentage in sorted_sources:
            count = sources_dict.get((domain, site_name), 0)
            rows.append(
                {
                    "site_name": site_name,
                    "domain": domain,
                    "count": count,
                    "percentage": f"{percentage:.1f}%",
                }
            )

        return rows

    def _prepare_products_rank_table_data(self, rank_level: int) -> list[dict]:
        """Prepare products table data by rank level"""
        if rank_level == 1:
            products_dict = self.stats.product_stats.rank1_products
            percentage_dict = self.stats.product_stats.rank1_product_percentage
        elif rank_level == 2:
            products_dict = self.stats.product_stats.top2_products
            percentage_dict = self.stats.product_stats.top2_product_percentage
        else:
            products_dict = self.stats.product_stats.top3_products
            percentage_dict = self.stats.product_stats.top3_product_percentage

        sorted_products = sorted(
            percentage_dict.items(), key=lambda x: x[1], reverse=True
        )[:20]

        rows = []
        for product, percentage in sorted_products:
            count = products_dict.get(product, 0)
            rows.append(
                {"product": product, "count": count, "percentage": f"{percentage:.1f}%"}
            )

        return rows

    def _prepare_target_product_data(self) -> dict:
        """Prepare target product data"""
        t = self.stats.target_product_stats
        if not t:
            return None

        best_keywords = [
            {"keyword": keyword, "rank": rank} for keyword, rank in t.best_keywords
        ]

        # Calculate rates based on total appearances
        rank1_rate = (t.rank1_count / t.total_appearances * 100) if t.total_appearances > 0 else 0
        top2_rate = (t.top2_count / t.total_appearances * 100) if t.total_appearances > 0 else 0
        top3_rate = (t.top3_count / t.total_appearances * 100) if t.total_appearances > 0 else 0

        return {
            "target_name": t.target_name,
            "total_appearances": t.total_appearances,
            "appearance_rate": f"{t.appearance_rate:.1f}",
            "rank1_count": t.rank1_count,
            "rank1_rate": f"{rank1_rate:.1f}",
            "top2_count": t.top2_count,
            "top2_rate": f"{top2_rate:.1f}",
            "top3_count": t.top3_count,
            "top3_rate": f"{top3_rate:.1f}",
            "average_rank": f"{t.average_rank:.2f}",
            "best_keywords": best_keywords,
        }

    def _load_raw_results(self) -> list[dict]:
        """Load raw results from JSONL (preferred) or CSV (fallback)."""
        if self._raw_results is not None:
            return self._raw_results

        jsonl_path = self.run_dir / "results.jsonl"
        csv_path = self.run_dir / "results.csv"

        results: list[dict] = []
        if jsonl_path.exists():
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))
        elif csv_path.exists():
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    success_raw = (row.get("success") or "").strip().lower()
                    success = success_raw in {"1", "true", "yes", "y"}
                    try:
                        rankings = json.loads(row.get("rankings") or "[]")
                    except Exception:
                        rankings = []
                    try:
                        sources = json.loads(row.get("sources") or "[]")
                    except Exception:
                        sources = []

                    results.append(
                        {
                            "keyword": row.get("keyword", ""),
                            "timestamp": row.get("timestamp", ""),
                            "success": success,
                            "error_message": row.get("error_message"),
                            "content": row.get("content", ""),
                            "rankings": rankings or [],
                            "sources": sources or [],
                        }
                    )
        else:
            results = []

        self._raw_results = results
        return results

    def _is_target_product(self, product_name: str) -> bool:
        """Check if product matches target (fuzzy substring match)"""
        if not self.stats.target_product_stats:
            return False
        target = self.stats.target_product_stats.target_name
        return target.lower() in product_name.lower()

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url

    def _prepare_all_cited_sources_data(self) -> dict:
        """Prepare data for all sources cited by LLM in rankings"""
        results = self._load_raw_results()
        source_counter = Counter()
        total_queries = 0

        for result in results:
            if not result.get("success"):
                continue

            total_queries += 1
            for ranking in result.get("rankings", []):
                for source in ranking.get("sources", []):
                    domain = self._extract_domain(source.get("url", ""))
                    site_name = source.get("site_name", domain)
                    source_key = (domain, site_name)
                    source_counter[source_key] += 1

        # Prepare chart data (top 10)
        sorted_sources = sorted(
            source_counter.items(), key=lambda x: x[1], reverse=True
        )[:10]

        chart_labels = []
        chart_data = []
        for (domain, site_name), count in sorted_sources:
            label = f"{site_name} ({domain})" if site_name != domain else domain
            chart_labels.append(label)
            chart_data.append(count)

        # Prepare table data (top 20)
        table_sources = sorted(
            source_counter.items(), key=lambda x: x[1], reverse=True
        )[:20]

        table_rows = []
        for (domain, site_name), count in table_sources:
            percentage = (count / total_queries * 100) if total_queries > 0 else 0
            table_rows.append(
                {
                    "site_name": site_name,
                    "domain": domain,
                    "count": count,
                    "percentage": f"{percentage:.1f}%",
                }
            )

        return {
            "chart": {"labels": chart_labels, "data": chart_data},
            "table": table_rows,
        }

    def _prepare_all_search_sources_data(self) -> dict:
        """Prepare data for all sources from search results (including uncited)"""
        results = self._load_raw_results()
        source_counter = Counter()
        total_queries = 0

        for result in results:
            if not result.get("success"):
                continue

            total_queries += 1
            # Count all sources from the raw search results
            for source in result.get("sources", []):
                domain = self._extract_domain(source.get("url", ""))
                site_name = source.get("site_name", domain)
                source_key = (domain, site_name)
                source_counter[source_key] += 1

        # Prepare chart data (top 10)
        sorted_sources = sorted(
            source_counter.items(), key=lambda x: x[1], reverse=True
        )[:10]

        chart_labels = []
        chart_data = []
        for (domain, site_name), count in sorted_sources:
            label = f"{site_name} ({domain})" if site_name != domain else domain
            chart_labels.append(label)
            chart_data.append(count)

        # Prepare table data (top 20)
        table_sources = sorted(
            source_counter.items(), key=lambda x: x[1], reverse=True
        )[:20]

        table_rows = []
        for (domain, site_name), count in table_sources:
            percentage = (count / total_queries * 100) if total_queries > 0 else 0
            table_rows.append(
                {
                    "site_name": site_name,
                    "domain": domain,
                    "count": count,
                    "percentage": f"{percentage:.1f}%",
                }
            )

        return {
            "chart": {"labels": chart_labels, "data": chart_data},
            "table": table_rows,
        }

    def _prepare_all_products_data(self) -> dict:
        """Prepare data for all products displayed by LLM"""
        results = self._load_raw_results()
        product_counter = Counter()
        total_queries = 0

        for result in results:
            if not result.get("success"):
                continue

            total_queries += 1
            for ranking in result.get("rankings", []):
                product_name = ranking.get("name", "")
                if product_name:
                    product_counter[product_name] += 1

        # Prepare chart data (top 10)
        sorted_products = sorted(
            product_counter.items(), key=lambda x: x[1], reverse=True
        )[:10]

        chart_labels = [p for p, _ in sorted_products]
        chart_data = [c for _, c in sorted_products]

        # Prepare table data (top 20)
        table_products = sorted(
            product_counter.items(), key=lambda x: x[1], reverse=True
        )[:20]

        table_rows = []
        for product, count in table_products:
            percentage = (count / total_queries * 100) if total_queries > 0 else 0
            table_rows.append(
                {"product": product, "count": count, "percentage": f"{percentage:.1f}%"}
            )

        return {
            "chart": {"labels": chart_labels, "data": chart_data},
            "table": table_rows,
        }

    def _prepare_target_product_sources(self) -> dict:
        """Prepare source distribution for target product"""
        if not self.stats.target_product_stats:
            return None

        # Count sources that cited the target product
        source_counter = Counter()
        results = self._load_raw_results()

        for result in results:
            if not result.get("success"):
                continue

            for ranking in result.get("rankings", []):
                product_name = ranking.get("name", "")
                if self._is_target_product(product_name):
                    for source in ranking.get("sources", []):
                        domain = self._extract_domain(source.get("url", ""))
                        site_name = source.get("site_name", domain)
                        source_key = (domain, site_name)
                        source_counter[source_key] += 1

        # Prepare chart data
        sorted_sources = sorted(
            source_counter.items(), key=lambda x: x[1], reverse=True
        )[:10]

        chart_labels = []
        chart_data = []
        for (domain, site_name), count in sorted_sources:
            label = f"{site_name} ({domain})" if site_name != domain else domain
            chart_labels.append(label)
            chart_data.append(count)

        # Prepare table data
        table_rows = []
        for (domain, site_name), count in sorted_sources:
            table_rows.append(
                {"site_name": site_name, "domain": domain, "count": count}
            )

        return {"chart": {"labels": chart_labels, "data": chart_data}, "table": table_rows}

    def _prepare_target_product_raw_data(self) -> list[dict]:
        """Prepare keyword-level data for target product (including keywords where it didn't appear)"""
        if not self.stats.target_product_stats:
            return None

        results = self._load_raw_results()
        raw_data = []

        for result in results:
            keyword = result.get("keyword", "")

            if not result.get("success"):
                # Failed query
                raw_data.append(
                    {
                        "keyword": keyword,
                        "rank": "查询失败",
                        "sources": "-",
                    }
                )
                continue

            # Check if target product appears in this keyword's rankings
            found = False
            for ranking in result.get("rankings", []):
                product_name = ranking.get("name", "")
                if self._is_target_product(product_name):
                    rank = ranking.get("rank", "")
                    sources_list = []
                    for source in ranking.get("sources", []):
                        site_name = source.get("site_name", "")
                        domain = self._extract_domain(source.get("url", ""))
                        sources_list.append(f"{site_name} ({domain})")

                    raw_data.append(
                        {
                            "keyword": keyword,
                            "rank": str(rank),
                            "sources": ", ".join(sources_list) if sources_list else "-",
                        }
                    )
                    found = True
                    break

            # If target product not found in rankings
            if not found:
                raw_data.append(
                    {
                        "keyword": keyword,
                        "rank": "未出现",
                        "sources": "-",
                    }
                )

        return raw_data

    def _prepare_all_keywords_raw_data(self) -> list[dict]:
        """Prepare keyword-level data for all search results"""
        results = self._load_raw_results()
        raw_data = []

        for result in results:
            keyword = result.get("keyword", "")
            if not result.get("success"):
                raw_data.append(
                    {
                        "keyword": keyword,
                        "success": False,
                        "rankings": [],
                    }
                )
                continue

            rankings_list = []
            for ranking in result.get("rankings", []):
                product_name = ranking.get("name", "")
                rank = ranking.get("rank", "")
                sources_list = []
                for source in ranking.get("sources", []):
                    site_name = source.get("site_name", "")
                    domain = self._extract_domain(source.get("url", ""))
                    sources_list.append(f"{site_name} ({domain})")

                rankings_list.append(
                    {
                        "rank": rank,
                        "product": product_name,
                        "sources": ", ".join(sources_list),
                    }
                )

            raw_data.append(
                {
                    "keyword": keyword,
                    "success": True,
                    "rankings": rankings_list,
                }
            )

        return raw_data

    def generate_console_summary(self) -> str:
        """Generate console summary"""
        return f"""
分析完成！

任务：{self.stats.job_name}
运行ID：{self.stats.run_id}
总关键词：{self.stats.total_keywords}
成功查询：{self.stats.successful_queries}
失败查询：{self.stats.failed_keywords}

报告已保存至：{self.run_dir}/
  - statistics.json
  - report.html
  - report.txt
"""

    def _format_source_section(
        self,
        *,
        title: str,
        sources_dict: dict[tuple[str, str], int],
        percentage_dict: dict[tuple[str, str], float],
        max_rows: int = 20,
    ) -> list[str]:
        sub_sep = "-" * 52
        lines = [title, sub_sep]

        sorted_items = sorted(
            percentage_dict.items(), key=lambda x: x[1], reverse=True
        )[:max_rows]

        if not sorted_items:
            lines.append("（无数据）")
            return lines

        for (domain, site_name), pct in sorted_items:
            count = sources_dict.get((domain, site_name), 0)
            label = f"{site_name} ({domain})" if site_name != domain else domain
            lines.append(f"{label:<30} {pct:>5.1f}% ({count}次)")

        return lines

    def _format_product_section(
        self,
        *,
        title: str,
        products_dict: dict[str, int],
        percentage_dict: dict[str, float],
        max_rows: int = 20,
    ) -> list[str]:
        sub_sep = "-" * 52
        lines = [title, sub_sep]

        sorted_items = sorted(
            percentage_dict.items(), key=lambda x: x[1], reverse=True
        )[:max_rows]

        if not sorted_items:
            lines.append("（无数据）")
            return lines

        for product, pct in sorted_items:
            count = products_dict.get(product, 0)
            lines.append(f"{product:<30} {pct:>5.1f}% ({count}次)")

        return lines

    def _serialize_stats(self, obj: Any) -> Any:
        """Convert tuple keys to strings for JSON serialization"""
        if isinstance(obj, dict):
            new_dict = {}
            for key, value in obj.items():
                if isinstance(key, tuple):
                    # Convert tuple (domain, site_name) to string
                    new_key = f"{key[1]} ({key[0]})" if key[0] != key[1] else key[0]
                else:
                    new_key = key
                new_dict[new_key] = self._serialize_stats(value)
            return new_dict
        elif isinstance(obj, list):
            return [self._serialize_stats(item) for item in obj]
        else:
            return obj
