"""LLM configuration loader"""

import json
import logging
import random
from pathlib import Path

from llm import OpenAIWrapper

logger = logging.getLogger(__name__)


def load_llm_configs(config_path: str | Path = "config.json") -> list[dict]:
    """Load LLM configurations from config file

    Args:
        config_path: Path to config.json

    Returns:
        List of LLM configuration dictionaries
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        llm_configs = config.get('llm', [])

        if not llm_configs:
            logger.warning("No LLM configurations found in config file")

        return llm_configs

    except Exception as e:
        logger.error(f"Failed to load LLM configs: {e}")
        return []


def create_random_llm_wrapper(config_path: str | Path = "config.json") -> OpenAIWrapper | None:
    """Create an OpenAI wrapper using a randomly selected LLM config

    Args:
        config_path: Path to config.json

    Returns:
        OpenAIWrapper instance or None if no configs available
    """
    llm_configs = load_llm_configs(config_path)

    if not llm_configs:
        logger.warning("No LLM configurations available")
        return None

    # Randomly select one config
    config = random.choice(llm_configs)

    logger.info(f"Selected LLM config: {config.get('model')} at {config.get('base_url')}")

    # Create wrapper
    try:
        wrapper = OpenAIWrapper(
            base_url=config['base_url'],
            api_key=config['api_key'],
            model=config['model'],
            timeout=config.get('timeout', 60.0),
            max_retries=config.get('max_retries', 2),
            organization=config.get('organization'),
            project=config.get('project'),
        )
        return wrapper

    except Exception as e:
        logger.error(f"Failed to create LLM wrapper: {e}")
        return None
