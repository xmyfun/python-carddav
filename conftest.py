"""Root pytest configuration: options that must exist before collection starts.

``pytest_addoption`` declared in a *subdirectory* ``conftest.py`` is registered too
late: without passing that directory explicitly on the command line, pytest fails
with "unrecognized arguments" before it ever loads the file. Options that apply to
the whole suite therefore live here, at ``rootdir``.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--allow-write",
        action="store_true",
        default=False,
        help=(
            "Enable write tests against live (pre-existing) servers. Local servers "
            "launched by the tests are always writable and ignore this flag."
        ),
    )
