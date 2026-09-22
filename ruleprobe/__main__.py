# SPDX-License-Identifier: MIT
"""`python -m ruleprobe`, the same entry point as the `ruleprobe` console script."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
