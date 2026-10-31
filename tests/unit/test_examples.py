"""Examples must stay runnable and must stick to the public API.

They are documentation, so they rot silently unless something executes them. ``--help`` is
enough to catch import errors, syntax errors and argument-parser regressions without
touching the network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "examples").glob("*.py"))


def test_examples_exist() -> None:
    assert EXAMPLES, "examples/ is empty"


def test_examples_help_runs() -> None:
    for script in EXAMPLES:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"
        assert "usage:" in result.stdout, f"{script.name}: no argparse output"


def test_examples_use_the_public_api_only() -> None:
    for script in EXAMPLES:
        text = script.read_text(encoding="utf-8")
        assert "from carddav._" not in text, f"{script.name} imports a private module"
        assert "import carddav._" not in text, f"{script.name} imports a private module"
