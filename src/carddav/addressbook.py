"""The AddressBook object - a collection of contact resources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from . import _dav, _naming, _xml
from .card import Card, extract_uid, uid_to_resource_name
from .errors import DAVError, MissingUIDError

if TYPE_CHECKING:  # pragma: no cover
    import xml.etree.ElementTree as ET

    from .client import DAVClient

MAX_HREF_IN_MULTIGET = 50


def _resolve_post_href(collection: str, location: str) -> str:
    """Turn a ``POST`` ``Location`` into a usable absolute href for *collection*.

    Servers return the new member's URL in one of two shapes:

    * a correct absolute URL, or a collection-relative URL - ``urljoin`` handles
      both directly;
    * a malformed **protocol-relative** URL where the collection path's first
      segment was mistaken for a host. Xandikos 0.4.10, for a collection served at
      ``/user/contacts/addressbook/``, returns
      ``//user/contacts/addressbook/<uuid>.vcf``; ``urljoin`` then yields
      ``http://user/...`` (wrong host, unresolvable). When the joined URL's host
      does not match the collection's, reconstruct from the collection plus the
      ``Location``'s trailing path segment (the real resource name).
    """
    joined = urljoin(collection, location)
    coll = urlsplit(collection)
    j = urlsplit(joined)
    if j.netloc and j.netloc != coll.netloc:
        last = location.rstrip("/").rsplit("/", 1)[-1]
        return urljoin(collection, last)
    return joined


@dataclass
class Change:
    """One entry of a ``sync-collection`` result. Read-only."""

    href: str
    etag: str | None
    deleted: bool


def _cards_from(root: ET.Element, base_url: str) -> list[Card]:
    """Turn a multistatus into cards, skipping the collection's own response.

    Shared by PROPFIND listings, ``addressbook-multiget`` and
    ``addressbook-query`` - the response shape is the same (RFC 6352 section 8.6/section 8.7).
    """
    cards: list[Card] = []
    for resp in _xml.iter_responses(root):
        raw = _xml.response_href(resp)
        if not raw:
            continue
        href = urljoin(base_url, raw)
        if href.rstrip("/") == base_url.rstrip("/"):
            continue
        # RFC 6352 section 5.2(a): an address book may contain collections that are not
        # address books. Those are not cards - skip them when the server tells us
        # the resourcetype (PROPFIND does; multiget responses normally don't).
        if _xml.response_has(resp, _xml.DAV_NS, "collection"):
            continue
        etag = _xml.find_text(resp, _xml.DAV_NS, "getetag")
        data_node = resp.find(f".//{_xml._q(_xml.CARDDAV_NS, 'address-data')}")
        data = data_node.text.encode("utf-8") if data_node is not None and data_node.text else None
        cards.append(Card(href=href, etag=etag, data=data, uid=extract_uid(data) if data else None))
    return cards


class AddressBook:
    """A single addressbook collection identified by its ``url``."""

    def __init__(
        self,
        client: DAVClient,
        url: str,
        *,
        display_name: str = "",
        ctag: str | None = None,
    ) -> None:
        self.client = client
        # Normalize to a trailing slash so that urljoin(self.url, child) always
        # resolves *under* the collection (urljoin treats a non-slash base's last
        # segment as a file and would otherwise drop it - see issue with PUT URLs).
        self.url = url.rstrip("/") + "/"
        self.display_name = display_name
        self.ctag = ctag

    def get_cards(self) -> list[Card]:
        """List all cards (one ``PROPFIND`` Depth:1) - href + etag only.

        PROPFIND cannot return ``address-data``, so ``Card.uid``/``Card.data``
        stay ``None`` here; use :meth:`get_all_cards` when you need the vCard.
        """
        root = _dav.propfind(self.client.transport, self.url, _xml.propfind_cards(), depth="1")
        return _cards_from(root, self.url)

    def get_card(self, href: str) -> Card:
        """Fetch one card by href; returns raw bytes + etag + uid."""
        href = urljoin(self.url, href)
        data, etag = _dav.get_bytes(self.client.transport, href)
        return Card(href=href, etag=etag, data=data, uid=extract_uid(data))

    def get_changes(self, sync_token: str | None = None) -> tuple[list[Change], str | None]:
        """``sync-collection`` (RFC 6578). Returns (changes, new_token)."""
        root = _dav.report(
            self.client.transport, self.url, _xml.report_sync_collection(sync_token), depth="1"
        )
        new_token = _xml.find_text(root, _xml.DAV_NS, "sync-token")
        changes: list[Change] = []
        for resp in _xml.iter_responses(root):
            raw = _xml.response_href(resp)
            if not raw:
                continue
            href = urljoin(self.url, raw)
            status = _xml.find_text(resp, _xml.DAV_NS, "status")
            deleted = bool(status and "404" in status)
            # RFC 6578 section 3.6: a server that truncates the result reports the
            # limit against the *collection* itself (507) instead of listing a
            # member. The collection is not an address object, so skip it.
            if not deleted and href.rstrip("/") == self.url.rstrip("/"):
                continue
            etag = _xml.find_text(resp, _xml.DAV_NS, "getetag")
            changes.append(Change(href=href, etag=etag, deleted=deleted))
        return changes, new_token

    # ---- batch read --------------------------------------------------------

    def multiget(self, hrefs: list[str]) -> list[Card]:
        """Fetch several cards by href in one ``addressbook-multiget`` REPORT.

        Returns :class:`Card` objects with ``data`` populated (the server returns
        each vCard's address-data inline). Order is not guaranteed to match
        *hrefs*; callers should key by ``href``/``uid``.

        Sends ``Depth: 0`` as RFC 6352 section 8.7 requires ("The request MUST include
        a Depth: 0 header"); the scope is defined by the ``DAV:href`` list, not
        by Depth.
        """
        if not hrefs:
            return []
        root = _dav.report(self.client.transport, self.url, _xml.report_multiget(hrefs), depth="0")
        return _cards_from(root, self.url)

    def get_all_cards(self) -> list[Card]:
        """List and fetch the full vCard of every card, via ``multiget`` batches.

        Unlike :meth:`get_cards` (href/etag only), this returns cards with
        ``data`` populated. Batched in groups of ``MAX_HREF_IN_MULTIGET``.
        """
        listed = self.get_cards()
        if not listed:
            return []
        cards: list[Card] = []
        for i in range(0, len(listed), MAX_HREF_IN_MULTIGET):
            batch = [c.href for c in listed[i : i + MAX_HREF_IN_MULTIGET]]
            cards.extend(self.multiget(batch))
        return cards

    def search(self, xml: str, *, depth: str = "1") -> list[Card]:
        """Run a raw ``addressbook-query`` REPORT (RFC 6352 section 8.6).

        The body is sent **verbatim**: this library builds no filter model
        (``internal/02`` section 9), so the caller owns the ``CARDDAV:filter`` /
        ``text-match`` / ``CARDDAV:limit`` XML - including namespaces and the
        default collation.

        ``depth``: section 8.6 requires a ``Depth`` header; querying a whole collection
        uses ``"1"`` (or ``"infinity"``). Note this is **not** the ``"0"`` that
        :meth:`multiget` must send (section 8.7) - mixing them up is the common mistake.

        Returns matching cards with ``data`` populated. Truncation is not
        signalled yet: a server that caps results returns partial matches plus a
        ``507`` on the collection (RFC 6352 section 8.6.2), see ``internal/09`` section 5.
        """
        if not xml.strip():
            raise ValueError("search() needs a complete addressbook-query XML body")
        root = _dav.report(self.client.transport, self.url, xml, depth=depth)
        return _cards_from(root, self.url)

    # ---- writes ------------------------------------------------------------

    def put_card(
        self,
        data: bytes,
        *,
        href: str | None = None,
        if_match: str | None = None,
        create_only: bool = False,
    ) -> str | None:
        """Create or replace a card (``PUT``).

        This is the **standard CardDAV create/update path** (RFC 6352 section 6.3.2:
        PUT to an unmapped URI creates, to a mapped URI updates).

        ``href``: the resource to write. **Pass the card's existing href when
        updating** - the spec says resource names are "entirely arbitrary", so a
        card created by another client (or by the server via POST) may not be at
        ``<uid>.vcf``; PUTting to a *different* URL creates a second resource
        instead of updating that card. When omitted we derive ``<uid>.vcf`` from
        the card's UID (stable, idempotent default), **percent-encoding** the UID
        first: the UID stays recoverable (``unquote`` round-trips it) while ``/``
        becomes ``%2F`` and ``:`` becomes ``%3A``, so a crafted UID can neither
        escape the collection nor be parsed as a URI scheme.

        ``if_match``: pass the card's current etag for a safe update. On mismatch
        the server returns **412** and we raise :class:`PreconditionFailed` - no
        auto-retry, no silent overwrite (``internal/02`` section 6).
        ``create_only``: when True, send ``If-None-Match: *`` so the server
        rejects the request with **412** if the URL already exists (RFC 6352
        section 6.3.2 SHOULD for "intend to create a new resource"). Mutually exclusive
        with ``if_match``.

        Returns the server's new ETag (from the response headers), or ``None`` if
        the server omitted it.
        """
        if create_only and if_match is not None:
            raise ValueError("create_only and if_match are mutually exclusive")
        if href is None:
            uid = extract_uid(data)
            if uid is None:
                raise MissingUIDError(
                    "cannot derive a resource name without a UID "
                    "(pass href= to target an existing card instead)"
                )
            name = uid_to_resource_name(uid)
            if name is None:
                raise MissingUIDError(
                    "the UID is empty, so no resource name can be derived "
                    "(pass href= to target an existing card instead)"
                )
            href = f"{name}.vcf"
        url = urljoin(self.url, href)
        headers = {"Content-Type": "text/vcard; charset=utf-8"}
        if if_match is not None:
            headers["If-Match"] = if_match
        if create_only:
            headers["If-None-Match"] = "*"
        resp = _dav.request(
            self.client.transport,
            "PUT",
            url,
            body=data.decode("utf-8"),
            headers=headers,
        )
        return resp.headers.get("ETag")

    def post_card(self, data: bytes, *, content_type: str = "text/vcard") -> str:
        """Create a card by asking the server to assign the URL (``POST``).

        This is a **plain POST to the collection**. It is:

        * **not** RFC 6352 - that spec only defines ``PUT`` for creating cards;
        * **not** RFC 5995 - the standardised "add member" flow requires
          discovering ``DAV:add-member`` first, which this library does not do.

        Server support is uneven and **not** guaranteed:

        * Radicale answers ``405`` and Synology ``500`` - ``POST`` is not a create
          path there, so :meth:`put_card` is the only option.
        * Xandikos 0.4.10 answers ``200`` with a ``Location`` header, but the
          ``Location`` is a malformed protocol-relative URL
          (``//user/contacts/addressbook/<uuid>.vcf``) whose host was taken from the
          collection path's first segment. The library reconstructs a usable absolute
          href from the collection plus the ``Location``'s trailing segment, so
          ``POST`` *is* a working create path on Xandikos (verified 2026-10-30).

        Returns the new card's href (resolved from the ``Location`` header).
        Prefer :meth:`put_card` - it is the standard RFC 6352 path and the only one
        that works on every server we tested.
        """
        headers = {"Content-Type": f"{content_type}; charset=utf-8"}
        resp = _dav.request(
            self.client.transport,
            "POST",
            self.url,
            body=data.decode("utf-8"),
            headers=headers,
        )
        location = resp.headers.get("Location")
        if not location:
            raise DAVError("POST did not return a Location header (server-assigned URL missing)")
        return _resolve_post_href(self.url, location)

    def delete_card(self, href: str, *, if_match: str | None = None) -> None:
        """Delete a card (``DELETE``).

        ``if_match`` guards against deleting a newer version created by someone
        else since we last read the card.
        """
        url = urljoin(self.url, href)
        headers: dict[str, str] = {}
        if if_match is not None:
            headers["If-Match"] = if_match
        _dav.request(self.client.transport, "DELETE", url, headers=headers)

    # ---- export ------------------------------------------------------------

    def export(self, path: str | Path, *, per_card: bool = False) -> Path:
        """Write all cards to disk.

        Default: a single ``.vcf`` bundle (multiple ``BEGIN:VCARD`` blocks).
        ``per_card=True``: one file per card named ``<uid>.vcf`` under *path*. The
        UID comes from the server and is sanitized for the filesystem, so it can
        never escape *path* or introduce a nested directory.

        Only ``data`` is written - the library performs no vCard parsing or
        re-serialization, so the bytes are exactly what the server returned.
        """
        cards = self.get_all_cards()
        out = Path(path)
        if per_card:
            out.mkdir(parents=True, exist_ok=True)
            for c in cards:
                name = f"{_naming.sanitize_component(c.uid, fallback='card')}.vcf"
                (out / name).write_bytes(c.data or b"")
            return out
        if not out.suffix:
            out = out.with_suffix(".vcf")
        with out.open("wb") as fh:
            for c in cards:
                if not c.data:
                    continue
                fh.write(c.data)
                if not c.data.endswith(b"\n"):
                    fh.write(b"\r\n")
        return out
