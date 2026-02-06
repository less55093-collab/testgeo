"""Test script for DeepSeek parser with ranking extraction"""

import asyncio
import logging
from pathlib import Path

from llm import create_random_llm_wrapper
from provider.providers.deepseek.parser import DeepSeekParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_parser():
    """Test the DeepSeek parser with the reference file"""

    # Load reference response
    reference_file = Path("reference/deepseek messages.txt")
    if not reference_file.exists():
        logger.error(f"Reference file not found: {reference_file}")
        return

    with open(reference_file, 'r', encoding='utf-8') as f:
        raw_response = f.read()

    logger.info(f"Loaded reference response ({len(raw_response)} bytes)")

    # Test 1: Parse response only (without LLM)
    logger.info("\n=== Test 1: Parse response without LLM ===")
    parser_without_llm = DeepSeekParser()
    result1 = await parser_without_llm.parse_response(raw_response)

    logger.info(f"Content:\n{result1.content}")
    logger.info(f"Content length: {len(result1.content)} characters")
    logger.info(f"Number of sources: {len(result1.sources)}")

    if result1.sources:
        logger.info("\nSources:")
        for i, source in enumerate(result1.sources, 1):
            logger.info(f"  [{i}] {source.get('title')} - {source.get('url')}")

    # Test 2: Parse with LLM ranking extraction
    logger.info("\n=== Test 2: Parse with LLM ranking extraction ===")

    # Create LLM wrapper
    llm_wrapper = create_random_llm_wrapper()
    if not llm_wrapper:
        logger.warning("Could not create LLM wrapper. Skipping ranking extraction test.")
        logger.warning("Please configure LLM settings in config.json")
        return

    logger.info("LLM wrapper created successfully")

    # Create parser with LLM
    parser_with_llm = DeepSeekParser(llm_wrapper=llm_wrapper)

    # Parse full response
    logger.info("Starting full parse with ranking extraction...")
    result2 = await parser_with_llm.parse(raw_response)

    logger.info(f"Result:\n{result2.rankings}")
    logger.info(f"\nContent length: {len(result2.content)} characters")
    logger.info(f"Number of sources: {len(result2.sources)}")
    logger.info(f"Number of rankings: {len(result2.rankings)}")

    if result2.rankings:
        logger.info("\nExtracted rankings:")
        for ranking in result2.rankings:
            name = ranking.get('name')
            rank = ranking.get('rank')
            sources = ranking.get('sources', [])
            source_indices = [i+1 for i, s in enumerate(result2.sources) if s in sources]

            if sources:
                logger.info(f"  Rank {rank}: {name} (sources: {','.join(map(str, source_indices))})")
            else:
                logger.info(f"  Rank {rank}: {name}")

    # Clean up
    await llm_wrapper.close()

    logger.info("\n=== Test completed ===")


if __name__ == "__main__":
    asyncio.run(test_parser())
