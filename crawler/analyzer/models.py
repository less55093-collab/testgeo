"""
Data models for analyzer
"""

from dataclasses import dataclass, field


@dataclass
class SourceStatistics:
    """Statistics about source websites"""

    total_unique_sources: int
    source_appearances: dict[tuple[str, str], int] = field(default_factory=dict)
    rank1_sources: dict[tuple[str, str], int] = field(default_factory=dict)
    top2_sources: dict[tuple[str, str], int] = field(default_factory=dict)
    top3_sources: dict[tuple[str, str], int] = field(default_factory=dict)
    rank1_source_percentage: dict[tuple[str, str], float] = field(default_factory=dict)
    top2_source_percentage: dict[tuple[str, str], float] = field(default_factory=dict)
    top3_source_percentage: dict[tuple[str, str], float] = field(default_factory=dict)
    all_source_percentage: dict[tuple[str, str], float] = field(default_factory=dict)


@dataclass
class ProductStatistics:
    """Statistics about products/platforms"""

    total_unique_products: int
    product_appearances: dict[str, int] = field(default_factory=dict)
    rank1_products: dict[str, int] = field(default_factory=dict)
    top2_products: dict[str, int] = field(default_factory=dict)
    top3_products: dict[str, int] = field(default_factory=dict)
    rank1_product_percentage: dict[str, float] = field(default_factory=dict)
    top2_product_percentage: dict[str, float] = field(default_factory=dict)
    top3_product_percentage: dict[str, float] = field(default_factory=dict)
    all_product_percentage: dict[str, float] = field(default_factory=dict)


@dataclass
class TargetProductStatistics:
    """Statistics specific to user's target product"""

    target_name: str
    total_appearances: int
    rank1_count: int
    top2_count: int
    top3_count: int
    average_rank: float
    appearance_rate: float
    best_keywords: list[tuple[str, int]] = field(default_factory=list)
    worst_keywords: list[tuple[str, int]] = field(default_factory=list)
    rank_position_counts: dict[int, int] = field(default_factory=dict)


@dataclass
class OverallStatistics:
    """Top-level statistics container"""

    job_name: str
    run_id: str
    analyzed_at: str
    total_keywords: int
    successful_queries: int
    failed_keywords: int
    source_stats: SourceStatistics
    product_stats: ProductStatistics
    target_product_stats: TargetProductStatistics | None
    average_sources_per_keyword: float
    average_rankings_per_keyword: float


@dataclass
class KeywordResult:
    """Loaded keyword result"""

    keyword: str
    success: bool
    rankings: list[dict]
    sources: list[dict]
