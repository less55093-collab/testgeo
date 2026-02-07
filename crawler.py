"""
CLI entrypoint wrapper.

This project originally used `crawl.py`. The documentation refers to `crawler.py`,
so this file keeps both entrypoints working.
"""

import asyncio

from crawl import main


if __name__ == "__main__":
    asyncio.run(main())

