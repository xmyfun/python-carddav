"""Tests for the pluggable HTTP backend.

A backend is any object with ``request(...)`` / ``close()``, so a fake needs no
inheritance — this is also the recommended way to mock HTTP in downstream apps.
"""

from __future__ import annotations

from typing import Any

import pytest

from carddav import AddressBook, DAVClient, Response, TransportError
from carddav._http import Headers
from carddav._transport import Transport


def resp(
    status: int = 200,
    body: bytes = b"",
    headers: list[tuple[str, str]] | None = None,
    url: str = "http://h/",
) -> Response:
    return Response(
        status_code=status,
        content=body,
        text=body.decode("utf-8", "replace"),
        headers=Headers(headers or []),
        url=url,
    )


class FakeBackend:
    """Minimal Backend implementation; returns queued responses/errors."""

    name = "fake"

    def __init__(self, *items: object) -> None:
        self._items = list(items)
        self.calls: list[tuple[str, str, Any, Any]] = []
        self.closed = False

    def request(self, method, url, *, headers=None, content=None, follow_redirects=True):  # noqa: ANN001
        self.calls.append((method, url, headers, content))
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


PROPFIND_CARDS = (
    b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
    b'<d:response><d:href>/book/a.vcf</d:href><d:propstat><d:prop>'
    b'<d:getetag>"1"</d:getetag></d:prop></d:propstat></d:response>'
    b"</d:multistatus>"
)


def test_custom_backend_drives_the_library_end_to_end() -> None:
    backend = FakeBackend(resp(207, PROPFIND_CARDS, url="http://h/book/"))
    client = DAVClient("http://h/book/", backend=backend)
    book = AddressBook(client, "http://h/book/")

    cards = book.get_cards()

    assert [c.href for c in cards] == ["http://h/book/a.vcf"]
    assert backend.calls[0][0] == "PROPFIND"
    assert backend.calls[0][2]["Depth"] == "1"


def test_idempotent_read_is_retried_once() -> None:
    backend = FakeBackend(TransportError("boom"), resp(200, b"ok"))
    transport = Transport(backend)

    assert transport.request("GET", "http://h/x").content == b"ok"
    assert len(backend.calls) == 2


def test_write_is_never_retried() -> None:
    backend = FakeBackend(TransportError("boom"), resp(200, b"ok"))
    transport = Transport(backend)

    with pytest.raises(TransportError):
        transport.request("PUT", "http://h/x", content=b"data")
    assert len(backend.calls) == 1


def test_5xx_is_retried_for_idempotent_methods_only() -> None:
    backend = FakeBackend(resp(503), resp(200, b"ok"))
    transport = Transport(backend)
    assert transport.request("REPORT", "http://h/x").status_code == 200
    assert len(backend.calls) == 2

    backend2 = FakeBackend(resp(503))
    transport2 = Transport(backend2)
    assert transport2.request("PUT", "http://h/x", content=b"d").status_code == 503
    assert len(backend2.calls) == 1


def test_headers_are_case_insensitive() -> None:
    h = Headers([("ETag", '"abc"'), ("Content-Type", "text/vcard")])
    assert h.get("etag") == '"abc"'
    assert h["CONTENT-TYPE"] == "text/vcard"
    assert "Etag" in h


def test_close_delegates_to_the_backend() -> None:
    backend = FakeBackend()
    Transport(backend).close()
    assert backend.closed is True


def test_unknown_backend_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        DAVClient("http://h/book/", backend="urllib3")


def test_bare_host_stops_at_the_first_collection_hop() -> None:
    # Synology: /.well-known/carddav -> /carddav/ -> .web (a web page).
    backend = FakeBackend(resp(302, headers=[("Location", "http://h/carddav/")]))
    assert DAVClient("http://h", backend=backend).url == "http://h/carddav/"


def test_well_known_hop_to_a_web_page_is_not_used_as_base() -> None:
    backend = FakeBackend(
        resp(302, headers=[("Location", "/carddav")]),
        resp(302, headers=[("Location", ".web")]),
    )
    # "/carddav" (no dot in the last segment) wins over the ".web" page.
    assert DAVClient("http://h", backend=backend).url == "http://h/carddav"


def test_urls_with_a_path_are_never_probed() -> None:
    backend = FakeBackend()
    assert DAVClient("http://h/dav/u/book/", backend=backend).url == "http://h/dav/u/book/"
    assert backend.calls == []
