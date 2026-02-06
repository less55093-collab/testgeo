"""
Statistics calculator for ranking analysis
"""

from collections import Counter
from urllib.parse import urlparse

from crawler.analyzer.models import (
    KeywordResult,
    OverallStatistics,
    ProductStatistics,
    SourceStatistics,
    TargetProductStatistics,
)


class StatisticsCalculator:
    """Calculates statistics from results"""

    def calculate(
        self, results: list[KeywordResult], target_product: str | None
    ) -> OverallStatistics:
        """Calculate all statistics"""
        successful = [r for r in results if r.success]
        num_success = len(successful)

        if num_success == 0:
            # Return empty statistics
            return self._empty_statistics(len(results), target_product)

        # Accumulators
        source_counter: Counter = Counter()
        rank1_sources: Counter = Counter()
        top2_sources: Counter = Counter()
        top3_sources: Counter = Counter()

        product_counter: Counter = Counter()
        rank1_products: Counter = Counter()
        top2_products: Counter = Counter()
        top3_products: Counter = Counter()

        # Target product tracking
        target_ranks: list[int] = []
        target_keywords: dict[str, int] = {}

        total_sources_count = 0
        total_rankings_count = 0

        for result in successful:
            total_rankings_count += len(result.rankings)

            for ranking in result.rankings:
                rank = ranking.get("rank", 999)
                product_name = ranking.get("name", "")

                if not product_name:
                    continue

                # Track product
                product_counter[product_name] += 1
                if rank == 1:
                    rank1_products[product_name] += 1
                if rank <= 2:
                    top2_products[product_name] += 1
                if rank <= 3:
                    top3_products[product_name] += 1

                # Check if target product (fuzzy match)
                if self._is_target_product(product_name, target_product):
                    target_ranks.append(rank)
                    target_keywords[result.keyword] = rank

                # Track sources for this ranking
                for source in ranking.get("sources", []):
                    total_sources_count += 1
                    domain = self._extract_domain(source.get("url", ""))
                    site_name = source.get("site_name", domain)
                    source_key = (domain, site_name)

                    source_counter[source_key] += 1
                    if rank == 1:
                        rank1_sources[source_key] += 1
                    if rank <= 2:
                        top2_sources[source_key] += 1
                    if rank <= 3:
                        top3_sources[source_key] += 1

        # Calculate source statistics
        source_stats = SourceStatistics(
            total_unique_sources=len(source_counter),
            source_appearances=dict(source_counter),
            rank1_sources=dict(rank1_sources),
            top2_sources=dict(top2_sources),
            top3_sources=dict(top3_sources),
            rank1_source_percentage=self._calc_percentage(rank1_sources, num_success),
            top2_source_percentage=self._calc_percentage(top2_sources, num_success),
            top3_source_percentage=self._calc_percentage(top3_sources, num_success),
            all_source_percentage=self._calc_percentage(source_counter, num_success),
        )

        # Calculate product statistics
        product_stats = ProductStatistics(
            total_unique_products=len(product_counter),
            product_appearances=dict(product_counter),
            rank1_products=dict(rank1_products),
            top2_products=dict(top2_products),
            top3_products=dict(top3_products),
            rank1_product_percentage=self._calc_percentage(rank1_products, num_success),
            top2_product_percentage=self._calc_percentage(top2_products, num_success),
            top3_product_percentage=self._calc_percentage(top3_products, num_success),
            all_product_percentage=self._calc_percentage(product_counter, num_success),
        )

        # Calculate target product statistics
        target_stats = None
        if target_product and target_ranks:
            target_stats = TargetProductStatistics(
                target_name=target_product,
                total_appearances=len(target_ranks),
                rank1_count=sum(1 for r in target_ranks if r == 1),
                top2_count=sum(1 for r in target_ranks if r <= 2),
                top3_count=sum(1 for r in target_ranks if r <= 3),
                average_rank=sum(target_ranks) / len(target_ranks),
                appearance_rate=(len(target_ranks) / num_success * 100),
                best_keywords=sorted(target_keywords.items(), key=lambda x: x[1])[:5],
                worst_keywords=sorted(
                    target_keywords.items(), key=lambda x: x[1], reverse=True
                )[:5],
            )

        return OverallStatistics(
            job_name="",  # Will be set by caller
            run_id="",  # Will be set by caller
            analyzed_at="",  # Will be set by caller
            total_keywords=len(results),
            successful_queries=num_success,
            failed_keywords=len(results) - num_success,
            source_stats=source_stats,
            product_stats=product_stats,
            target_product_stats=target_stats,
            average_sources_per_keyword=(
                total_sources_count / num_success if num_success > 0 else 0
            ),
            average_rankings_per_keyword=(
                total_rankings_count / num_success if num_success > 0 else 0
            ),
        )

    def _is_target_product(self, product_name: str, target: str | None) -> bool:
        """Check if product matches target (fuzzy substring match)"""
        if not target:
            return False
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

    def _calc_percentage[T: (str, tuple[str, str])](
        self, counter: Counter[T], total: int
    ) -> dict[T, float]:
        """Calculate percentage for each item"""
        if total == 0:
            return {}
        return {item: (count / total * 100) for item, count in counter.items()}

    def _empty_statistics(
        self, total_keywords: int, target_product: str | None
    ) -> OverallStatistics:
        """Return empty statistics when no successful queries"""
        return OverallStatistics(
            job_name="",
            run_id="",
            analyzed_at="",
            total_keywords=total_keywords,
            successful_queries=0,
            failed_keywords=total_keywords,
            source_stats=SourceStatistics(total_unique_sources=0),
            product_stats=ProductStatistics(total_unique_products=0),
            target_product_stats=None,
            average_sources_per_keyword=0.0,
            average_rankings_per_keyword=0.0,
        )
