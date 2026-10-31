"""Shared helpers for the remote real-server tests (``servers.ini``).

Imported by ``conftest.py`` and ``_catalog.py`` - ``tests/integration`` is on
``sys.path`` during collection, so the bare module names resolve.
"""

from __future__ import annotations

import configparser
from pathlib import Path

_CONFIG = Path(__file__).with_name("servers.ini")


def load_creds(section: str):
    """Return ``(url, username, password, auth, verify)`` or ``None`` if unconfigured."""
    parser = configparser.ConfigParser(interpolation=None)
    if _CONFIG.exists():
        parser.read(_CONFIG)
    if not parser.has_section(section):
        return None
    url = parser.get(section, "url", fallback="").strip()
    username = parser.get(section, "username", fallback="").strip()
    password = parser.get(section, "password", fallback="").strip()
    if not url or not username:
        return None
    auth = parser.get(section, "auth", fallback="basic").strip().lower()
    verify = parser.getboolean(section, "verify", fallback=True)
    return url, username, password, auth, verify


def configured_sections() -> list[str]:
    """Sections present in ``servers.ini`` (used to parametrize the remote servers)."""
    parser = configparser.ConfigParser(interpolation=None)
    if _CONFIG.exists():
        parser.read(_CONFIG)
    return parser.sections()
