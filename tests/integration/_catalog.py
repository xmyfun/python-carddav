"""The server catalog: every server the integration suite runs against.

Two kinds of entry, and the difference is a property of the *server*, not of the
test:

* ``local`` - a local test server (Radicale / Xandikos) launched by the fixtures
  and destroyed when the session ends. A disposable sandbox: always writable.
* ``remote`` - a real remote server configured in ``servers.ini``. It exists
  independently of the test run and may hold real data, whether it sits on the
  public internet, on a LAN (e.g. Synology) or on localhost.

Tests are written once and run against every catalog entry.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from _helpers import configured_sections
from _profiles import KNOWN_PROFILES, ServerProfile


@dataclass(frozen=True)
class ServerSpec:
    id: str
    kind: str  # "local" | "remote"
    marks: tuple
    profile: ServerProfile | None


def _build() -> list[ServerSpec]:
    local = [
        ServerSpec(
            id=name,
            kind="local",
            marks=(pytest.mark.local,),
            profile=KNOWN_PROFILES.get(name),
        )
        for name in ("radicale", "xandikos")
    ]
    remote = [
        ServerSpec(
            id=section,
            kind="remote",
            marks=(pytest.mark.remote,),
            profile=KNOWN_PROFILES.get(section),
        )
        for section in configured_sections()
    ]
    return local + remote


CATALOG: list[ServerSpec] = _build()
