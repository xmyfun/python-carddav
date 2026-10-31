"""The Card resource object.

``Card.data`` is the **raw bytes** the server returned (decompressed, no charset
conversion) - never decoded, reordered, or re-folded. ``uid`` is extracted with a
minimal ``UID:`` line scan only; the library does not parse vCard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

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


def uid_to_resource_name(uid: str) -> str | None:
    """Percent-encode a UID into one safe URL path segment (None if empty).

    A UID is server-controlled input that ends up in a URL path. It is
    **encoded, not stripped**, so the UID stays recoverable -
    ``unquote(uid_to_resource_name(uid)) == uid``. Everything outside the
    unreserved set is encoded (``safe=""``): ``/`` becomes ``%2F`` and ``:``
    becomes ``%3A``, so the result is a single flat segment that can neither
    escape the collection nor be parsed as a URI scheme (``urn:uuid:...`` would
    otherwise leave HTTP entirely).
    """
    value = quote(uid.strip(), safe="")
    return value or None


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
