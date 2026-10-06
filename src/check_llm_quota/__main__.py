"""Allow ``python3 -m check_llm_quota``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
