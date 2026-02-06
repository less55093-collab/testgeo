"""
Logging configuration for crawler
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(log_file: Path):
    """Setup logging with framework logs suppressed to WARNING"""
    # Suppress framework logs
    logging.getLogger("provider").setLevel(logging.WARNING)
    logging.getLogger("llm").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("curl_cffi").setLevel(logging.WARNING)

    # Setup file logging for crawler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    crawler_logger = logging.getLogger("crawler")
    crawler_logger.setLevel(logging.INFO)
    crawler_logger.addHandler(file_handler)
