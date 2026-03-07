"""
nudgarr.py — compatibility shim for v2.8.0+

The app has been restructured into a package. This file exists so that
anyone running `python nudgarr.py` directly continues to work during
the transition. It will be removed in a future release.

Please update your start command to: python main.py
"""
import sys

print(
    "[Nudgarr] Warning: nudgarr.py is deprecated as of v2.8.0. "
    "Please update your start command to: python main.py",
    file=sys.stderr,
)

from main import main  # noqa: E402
main()
