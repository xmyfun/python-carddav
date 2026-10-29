"""The Card resource object.

``Card.data`` is the **raw bytes** the server returned (decompressed, no charset
conversion) - never decoded, reordered, or re-folded. ``uid`` is extracted with a
minimal ``UID:`` line scan only; the library does not parse vCard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UID_RE = re.compile(r"^UID(?:;[^:]*)?:(.*)$", re.MULTILINE)
_FOLD_RE = re.compile(r"\r?\n[ \t]")


def extract_uid(data: bytes) -> str | None:
    """Return the UID value (unfolded), or None. Minimal parse, no field model."""
    text = data.decode("utf-8", errors="replace")
    unfolded = _FOLD_RE.sub("", text)
    match = _UID_RE.search(unfolded)
    if match is None:
        return None
    return match.group(1).strip()


@dataclass
class Card:
    """A contact resource. ``href`` is the server-assigned URL (read-only)."""

    href: str
    etag: str | None = None
    data: bytes | None = None
    uid: str | None = None

    @property
    def text(self) -> str | None:
        """UTF-8 convenience view of ``data`` (``errors="replace"``)."""
        if self.data is None:
            return None
        return self.data.decode("utf-8", errors="replace")
