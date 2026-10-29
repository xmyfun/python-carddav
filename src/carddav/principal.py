"""The Principal object - the authenticated user's resource root."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

from . import _dav, _xml

if TYPE_CHECKING:  # pragma: no cover - avoid import cycle at runtime
    from .addressbook import AddressBook
    from .client import DAVClient


class Principal:
    """Represents ``current-user-principal``; owns the addressbook home-set."""

    def __init__(
        self,
        client: DAVClient,
        url: str,
        *,
        direct_addressbook: str | None = None,
    ) -> None:
        self.client = client
        self.url = url
        # Set when the entry URL was already a specific addressbook, so
        # get_addressbooks() can return it directly without further discovery.
        self._direct_addressbook = direct_addressbook

    def get_addressbooks(self) -> list[AddressBook]:
        """Discover and list the user's addressbook collections (RFC 6352).

        If the entry URL was already a specific addressbook, returns just that
        one. Otherwise it resolves the ``addressbook-home-set`` (which may live
        on a different host - this is normal per RFC 6352 section 7.1.1) and enumerates
        the addressbooks beneath it by ``resourcetype``.
        """
        from .addressbook import AddressBook

        if self._direct_addressbook is not None:
            return [AddressBook(self.client, self._direct_addressbook)]

        home = self._home_set_url()
        root = _dav.propfind(self.client.transport, home, _xml.propfind_addressbooks(), depth="1")
        books: list[AddressBook] = []
        for resp in _xml.iter_responses(root):
            raw = _xml.response_href(resp)
            if not raw:
                continue
            # Hrefs come from a PROPFIND on *home* and may be relative or point
            # at a different host (e.g. an iCloud carddavhome alias) - resolve
            # them against home, not against the principal URL.
            href = urljoin(home, raw)
            if href == home:
                continue
            if not _xml.response_has(resp, _xml.CARDDAV_NS, "addressbook"):
                continue
            display = _xml.find_text(resp, _xml.DAV_NS, "displayname")
            ctag = _xml.find_text(resp, _xml.CS_NS, "getctag")
            books.append(AddressBook(self.client, href, display_name=display or "", ctag=ctag))
        return books

    def _home_set_url(self) -> str:
        root = _dav.propfind(
            self.client.transport, self.url, _xml.propfind_addressbook_home_set(), depth="0"
        )
        # The home-set is usually carried in a nested <href>; fall back to the
        # element's text for servers that inline the URL.
        home = _xml.find_child_href(root, _xml.CARDDAV_NS, "addressbook-home-set")
        if home is None:
            home = _xml.find_text(root, _xml.CARDDAV_NS, "addressbook-home-set")
        if not home:
            # No home-set advertised (Synology, bare collections). The current
            # URL is the container that holds the addressbooks - enumerate it
            # directly rather than guessing it is a single addressbook.
            return self.url
        return urljoin(self.url, home)
