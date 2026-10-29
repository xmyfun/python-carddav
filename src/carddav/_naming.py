"""Filesystem-safe names for exported address books and cards (used by the CLI).

Two facts drive these rules:

* An address book's **identity is its collection URL**, not its ``displayname``
  (which may be empty - Synology returns ``""`` - or duplicated). Under one
  home-set the last path segment of every address book URL is unique, because
  WebDAV forbids two sibling resources with the same name. Single-account
  exports therefore never collide on the URL segment alone, so no hash suffix
  is needed.
* Both the ``displayname`` and the URL come from the server and are **untrusted
  input** that ends up in a path. They may contain ``/``, ``\\``, control
  characters, Windows reserved names, or be percent-encoded.

Naming (``internal/02`` section 1):

    folder / file name = "<displayname>(<slug>)"   # displayname non-empty
                       = "<slug>"                  # otherwise
    slug               = sanitize(unquote(last URL path segment))
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlparse

#: Hard cap on a single name component, in **UTF-8 bytes** (255 is the usual
#: filesystem limit; we leave room for a ``-2`` suffix and an extension).
MAX_NAME_BYTES = 200
#: The URL segment is the identity, so it keeps most of the budget.
MAX_SLUG_BYTES = 120
#: The display name is only a readable prefix, so it gets the rest.
MAX_DISPLAY_BYTES = 70

_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f\x7f]')
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _truncate_utf8(text: str, limit: int) -> str:
    """Cut *text* to at most *limit* UTF-8 bytes without splitting a character."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    raw = raw[:limit]
    while raw and (raw[-1] & 0xC0) == 0x80:  # drop trailing continuation bytes
        raw = raw[:-1]
    return raw.decode("utf-8", errors="ignore")


def sanitize_component(text: str | None, *, fallback: str = "book") -> str:
    """Turn one path segment into a safe, single-level file name component.

    The order matters: percent-decoding comes **first**, otherwise ``%2F`` would
    survive as a literal ``%2F`` and later become a real separator somewhere
    else. After decoding, ``/`` and ``\\`` are replaced so a decoded separator
    can never re-introduce a path level.
    """
    value = unicodedata.normalize("NFC", unquote(text or ""))
    value = value.replace("/", "_").replace("\\", "_")
    value = _ILLEGAL.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value or value in {".", ".."}:
        return fallback
    if value.split(".")[0].strip().casefold() in _RESERVED:
        value = "_" + value
    return _truncate_utf8(value, MAX_NAME_BYTES)


def _last_segment(url: str) -> str:
    """The last non-empty path segment of *url* (always a single segment)."""
    path = urlparse(url).path
    trimmed = path.rstrip("/")
    if not trimmed:
        return ""
    return trimmed.rsplit("/", 1)[-1]


def collection_slug(url: str, *, fallback: str = "book") -> str:
    """The address book's identity segment: ``sanitize(unquote(last segment))``."""
    return sanitize_component(_last_segment(url), fallback=fallback)


def book_dirname(display_name: str | None, url: str) -> str:
    """``"<displayname>(<slug>)"``, or just ``"<slug>"`` when there is no name."""
    slug = _truncate_utf8(collection_slug(url), MAX_SLUG_BYTES)
    display = sanitize_component(display_name, fallback="") if display_name else ""
    if not display:
        return slug
    display = _truncate_utf8(display, MAX_DISPLAY_BYTES)
    return f"{display}({slug})"


def href_filename(href: str, *, fallback: str = "card") -> str:
    """A ``.vcf`` file name derived from the resource's server-assigned href."""
    name = sanitize_component(_last_segment(href), fallback=fallback)
    if name.casefold().endswith(".vcf"):
        return name
    return _truncate_utf8(name, MAX_NAME_BYTES - 4) + ".vcf"


def unique_name(name: str, taken: set[str]) -> str:
    """Append ``-2``, ``-3``... until *name* is unique in *taken* (case-folded).

    Only a safety net: within one home-set the URL segments are already unique,
    and sanitising them does not normally introduce collisions. *taken* holds
    case-folded names and is **not** modified here.
    """
    if name.casefold() not in taken:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot:  # no extension
        stem, ext = name, ""
    for index in range(2, 1000):
        candidate = f"{stem}-{index}" + (f".{ext}" if ext else "")
        if candidate.casefold() not in taken:
            return candidate
    raise ValueError(f"cannot find a unique name for {name!r}")
