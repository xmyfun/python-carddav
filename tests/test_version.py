"""Keep the single-source version honest.

``pyproject.toml`` (metadata) and ``carddav._version`` (runtime, also used for the
``User-Agent``) must never drift apart — a wheel whose METADATA says one thing and
whose ``__version__`` says another is a silent packaging bug.

``tomllib`` is 3.11+; on 3.10 the check is skipped rather than pulling in ``tomli``
just for a test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from carddav import __version__
from carddav._http import USER_AGENT

tomllib = pytest.importorskip("tomllib", reason="tomllib is stdlib from Python 3.11")
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_pyproject_version_matches_runtime_version() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__


def test_user_agent_carries_the_version() -> None:
    assert USER_AGENT == f"carddav/{__version__}"
