"""Single source of truth for the package version.

``pyproject.toml`` carries the same value; ``tests/test_version.py`` keeps the two
in sync so a release bump can never ship a wheel whose ``__version__`` - or whose
``User-Agent`` - disagrees with its metadata.
"""

__version__ = "0.2.0"
