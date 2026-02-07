"""
CLI entrypoint wrapper.

This project originally used `analyze.py`. The documentation refers to `analyzer.py`,
so this file keeps both entrypoints working.
"""

from analyze import main


if __name__ == "__main__":
    main()

