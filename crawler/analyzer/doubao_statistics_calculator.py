"""
Deprecated Doubao statistics calculator.

The analyzer pipeline is now provider-agnostic, so Doubao/DeepSeek share the same
statistics calculation logic. This module is kept for backward compatibility.
"""

from crawler.analyzer.statistics_calculator import StatisticsCalculator


class DoubaoStatisticsCalculator(StatisticsCalculator):
    """Backward-compatible alias of :class:`StatisticsCalculator`."""

