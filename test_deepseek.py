"""Test DeepSeek provider"""

import argparse
import asyncio
import logging

from provider.core.types import CallParams
from provider.providers.deepseek import DeepSeek

# Enable logging to see what's happening
logging.basicConfig(level=logging.INFO)


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test DeepSeek provider with ranking extraction"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="上海女健身教练上门",
        help="Prompt to send to DeepSeek (default: 上海女健身教练上门)",
    )
    args = parser.parse_args()

    print("Initializing DeepSeek...")
    deepseek = DeepSeek("config.json")

    print(f"\nMaking API call with prompt: {args.prompt}")
    params = CallParams(
        messages=args.prompt,
        enable_thinking=False,
        enable_search=True,
    )

    try:
        result = await deepseek.call(params)
        print("\n✅ SUCCESS!")

        # Print summary
        print(f"\nContent length: {len(result.content)} characters")
        print(f"Number of sources: {len(result.sources)}")
        print(f"Number of rankings: {len(result.rankings)}")

        # Print content preview
        if result.content:
            print(f"\nContent: {result.content}")

        # Print sources
        if result.sources:
            print(f"\nSources ({len(result.sources)} total):")
            for i, source in enumerate(result.sources, 1):
                title = source.get("title", "N/A")
                url = source.get("url", "N/A")
                print(f"  [{i}] {title}")
                print(f"      {url}")

        # Print rankings with formatting
        if result.rankings:
            print("\nExtracted Rankings:")
            for ranking in result.rankings:
                name = ranking.get("name")
                rank = ranking.get("rank")
                sources = ranking.get("sources", [])

                # Find source indices
                source_indices = [
                    i + 1 for i, s in enumerate(result.sources) if s in sources
                ]

                if sources:
                    print(f"  Rank {rank}: {name}")
                    print(f"           Sources: {', '.join(map(str, source_indices))}")
                    for idx in source_indices:
                        if 0 < idx <= len(result.sources):
                            source_obj = result.sources[idx - 1]
                            source_title = source_obj.get("title", "N/A")
                            source_site = source_obj.get("site_name", "Unknown")
                            print(
                                f"             - [{idx}] {source_title} ({source_site})"
                            )
                else:
                    print(f"  Rank {rank}: {name} (no sources)")
        else:
            print("\nNo rankings extracted")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
