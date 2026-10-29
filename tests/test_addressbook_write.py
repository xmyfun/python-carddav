"""Offline unit tests for AddressBook write/batch/export methods.

A fake transport records calls and returns canned DAV responses, so no network
or real server is touched. The fake mimics the Radicale/Synology response shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from carddav import AddressBook, MissingUIDError
from carddav.errors import DAVError, PreconditionFailed


class FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"", headers: dict | None = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.text = content.decode("utf-8", "replace")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def request(self, method, url, *, headers=None, content=None, follow_redirects=True):  # noqa: ANN001
        self.calls.append((method, url, headers, content))
        if method == "GET":
            return FakeResponse(
                200,
                b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:g\r\nFN:G\r\nEND:VCARD\r\n",
                {"ETag": '"g-etag"', "Content-Type": "text/vcard"},
            )
        if method == "PROPFIND":
            body = (
                b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                b'<d:response><d:href>/book/a.vcf</d:href>'
                b'<d:propstat><d:prop><d:getetag>"1"</d:getetag></d:prop></d:propstat></d:response>'
                b'<d:response><d:href>/book/b.vcf</d:href>'
                b'<d:propstat><d:prop><d:getetag>"2"</d:getetag></d:prop></d:propstat></d:response>'
                b"</d:multistatus>"
            )
            return FakeResponse(207, body)
        if method == "REPORT":  # addressbook-multiget
            body = (
                b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" '
                b'xmlns:c="urn:ietf:params:xml:ns:carddav">'
                b'<d:response><d:href>/book/a.vcf</d:href>'
                b'<d:propstat><d:prop><d:getetag>"1"</d:getetag>'
                b'<c:address-data>BEGIN:VCARD\r\nUID:a\r\nFN:A\r\nEND:VCARD\r\n</c:address-data>'
                b"</d:prop></d:propstat></d:response>"
                b'<d:response><d:href>/book/b.vcf</d:href>'
                b'<d:propstat><d:prop><d:getetag>"2"</d:getetag>'
                b'<c:address-data>BEGIN:VCARD\r\nUID:b\r\nFN:B\r\nEND:VCARD\r\n</c:address-data>'
                b"</d:prop></d:propstat></d:response>"
                b"</d:multistatus>"
            )
            return FakeResponse(207, body)
        if method == "PUT":
            return FakeResponse(201, b"", {"ETag": '"new-etag"'})
        if method == "POST":
            return FakeResponse(201, b"", {"Location": "/book/created.vcf"})
        if method == "DELETE":
            return FakeResponse(204, b"")
        return FakeResponse(200, b"")


class FakeClient:
    def __init__(self, transport: FakeTransport) -> None:
        self.transport = transport


def make_book() -> tuple[AddressBook, FakeTransport]:
    t = FakeTransport()
    return AddressBook(FakeClient(t), "http://h/book"), t


def test_multiget_parses_cards_and_requests_both_hrefs() -> None:
    book, t = make_book()
    cards = book.multiget(["/book/a.vcf", "/book/b.vcf"])
    assert len(cards) == 2
    assert {c.uid for c in cards} == {"a", "b"}
    assert cards[0].etag == '"1"'
    method, _url, _headers, data = t.calls[0]
    assert method == "REPORT"
    assert b"/book/a.vcf" in data and b"/book/b.vcf" in data


def test_search_sends_the_body_verbatim_with_depth_one() -> None:
    book, t = make_book()
    query = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
        "<d:prop><d:getetag/><c:address-data/></d:prop>"
        '<c:filter><c:prop-filter name="FN">'
        "<c:text-match>张</c:text-match></c:prop-filter></c:filter>"
        "</c:addressbook-query>"
    )
    cards = book.search(query)
    assert {c.uid for c in cards} == {"a", "b"}
    method, url, headers, data = t.calls[0]
    assert method == "REPORT"
    assert url == "http://h/book/"
    assert headers["Depth"] == "1"  # RFC 6352 §8.6 (NOT the 0 that multiget needs)
    assert headers["Content-Type"].startswith("application/xml")
    assert data == query.encode("utf-8")  # byte-for-byte, no re-serialization


def test_search_depth_is_overridable_and_empty_body_rejected() -> None:
    book, t = make_book()
    book.search("<c:addressbook-query/>", depth="infinity")
    assert t.calls[-1][2]["Depth"] == "infinity"
    with pytest.raises(ValueError):
        book.search("   ")


class _SubCollectionTransport(FakeTransport):
    """PROPFIND result that also lists a (non-addressbook) sub-collection."""

    def request(self, method, url, *, headers=None, content=None, follow_redirects=True):  # noqa: ANN001
        self.calls.append((method, url, headers, content))
        if method != "PROPFIND":
            return FakeResponse(207, b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"/>')
        body = (
            b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
            b'<d:response><d:href>/book/a.vcf</d:href><d:propstat><d:prop>'
            b'<d:getetag>"1"</d:getetag>'
            b"<d:resourcetype/></d:prop></d:propstat></d:response>"
            # RFC 6352 §5.2(a) allows a plain collection inside an address book
            b"<d:response><d:href>/book/sub/</d:href><d:propstat><d:prop>"
            b"<d:resourcetype><d:collection/></d:resourcetype>"
            b"</d:prop></d:propstat></d:response>"
            b'<d:response><d:href>/book/b.vcf</d:href><d:propstat><d:prop>'
            b'<d:getetag>"2"</d:getetag>'
            b"<d:resourcetype/></d:prop></d:propstat></d:response>"
            b"</d:multistatus>"
        )
        return FakeResponse(207, body)


def test_get_cards_skips_sub_collections() -> None:
    t = _SubCollectionTransport()
    book = AddressBook(FakeClient(t), "http://h/book")
    assert [c.href for c in book.get_cards()] == ["http://h/book/a.vcf", "http://h/book/b.vcf"]


def test_multiget_sends_depth_zero() -> None:
    # RFC 6352 §8.7: "The request MUST include a Depth: 0 header"
    book, t = make_book()
    book.multiget(["/book/a.vcf"])
    method, _url, headers, _data = t.calls[0]
    assert method == "REPORT"
    assert headers["Depth"] == "0"


def test_get_card_populates_etag_from_header() -> None:
    book, _t = make_book()
    card = book.get_card("/book/a.vcf")
    assert card.etag == '"g-etag"'
    assert card.uid == "g"
    assert card.data and b"UID:g" in card.data


class _SyncTransport(FakeTransport):
    def request(self, method, url, *, headers=None, content=None, follow_redirects=True):  # noqa: ANN001
        self.calls.append((method, url, headers, content))
        body = (
            b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
            # RFC 6578 §3.6: truncation is reported against the collection itself
            b"<d:response><d:href>/book/</d:href>"
            b"<d:status>HTTP/1.1 507 Insufficient Storage</d:status></d:response>"
            b'<d:response><d:href>/book/a.vcf</d:href><d:propstat><d:prop>'
            b'<d:getetag>"9"</d:getetag></d:prop></d:propstat></d:response>'
            b"<d:response><d:href>/book/gone.vcf</d:href>"
            b"<d:status>HTTP/1.1 404 Not Found</d:status></d:response>"
            b"<d:sync-token>tok-2</d:sync-token>"
            b"</d:multistatus>"
        )
        return FakeResponse(207, body)


def test_get_changes_skips_collection_entry_and_marks_deletes() -> None:
    t = _SyncTransport()
    book = AddressBook(FakeClient(t), "http://h/book")
    changes, token = book.get_changes("tok-1")
    assert token == "tok-2"
    assert [c.href for c in changes] == ["http://h/book/a.vcf", "http://h/book/gone.vcf"]
    assert changes[0].deleted is False and changes[0].etag == '"9"'
    assert changes[1].deleted is True and changes[1].etag is None
    _method, _url, headers, body = t.calls[0]
    assert headers["Depth"] == "1"
    assert b"<d:sync-token>tok-1</d:sync-token>" in body


def test_get_all_cards_batches_through_multiget() -> None:
    book, _t = make_book()
    cards = book.get_all_cards()
    assert len(cards) == 2
    assert {c.uid for c in cards} == {"a", "b"}


def test_put_card_without_uid_raises() -> None:
    book, _t = make_book()
    with pytest.raises(MissingUIDError):
        book.put_card(b"BEGIN:VCARD\r\nFN:no uid\r\nEND:VCARD")


def test_put_card_sends_if_match_content_type_and_uid_url() -> None:
    book, t = make_book()
    vcard = b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:u1\r\nFN:U\r\nEND:VCARD"
    etag = book.put_card(vcard, if_match='"abc"')
    assert etag == '"new-etag"'
    method, url, headers, data = t.calls[-1]
    assert method == "PUT"
    assert url.endswith("/u1.vcf")
    assert headers["If-Match"] == '"abc"'
    assert headers["Content-Type"].startswith("text/vcard")
    assert b"UID:u1" in data


def test_put_card_create_only_sends_if_none_match_star() -> None:
    book, t = make_book()
    vcard = b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:u2\r\nFN:U\r\nEND:VCARD"
    etag = book.put_card(vcard, create_only=True)
    assert etag == '"new-etag"'
    method, url, headers, _data = t.calls[-1]
    assert method == "PUT"
    assert url.endswith("/u2.vcf")
    assert headers.get("If-None-Match") == "*"
    assert "If-Match" not in headers  # create-only must not carry an etag match


def test_put_card_create_only_conflicts_with_if_match() -> None:
    book, _t = make_book()
    vcard = b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:u3\r\nFN:U\r\nEND:VCARD"
    with pytest.raises(ValueError):
        book.put_card(vcard, if_match='"abc"', create_only=True)


def test_put_card_explicit_href_targets_that_resource() -> None:
    # A card created by another client may live at a name that is *not* <uid>.vcf.
    # Updating it must PUT back to its real href, otherwise it becomes a 2nd card.
    book, t = make_book()
    vcard = b"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:u1\r\nFN:U\r\nEND:VCARD"
    book.put_card(vcard, href="/book/server-assigned-42.vcf", if_match='"1"')
    method, url, headers, _data = t.calls[-1]
    assert method == "PUT"
    assert url == "http://h/book/server-assigned-42.vcf"
    assert headers["If-Match"] == '"1"'
    assert headers.get("If-None-Match") is None


def test_put_card_explicit_href_does_not_require_uid() -> None:
    # With an explicit target the URL no longer depends on the UID, so a UID is
    # not needed to address the resource (RFC 6352 still requires one in the card).
    book, t = make_book()
    book.put_card(b"BEGIN:VCARD\r\nFN:no uid\r\nEND:VCARD", href="/book/x.vcf")
    _method, url, _headers, _data = t.calls[-1]
    assert url == "http://h/book/x.vcf"


def test_post_card_returns_resolved_location() -> None:
    book, t = make_book()
    href = book.post_card(b"BEGIN:VCARD\r\nUID:x\r\nFN:X\r\nEND:VCARD")
    assert href == "http://h/book/created.vcf"
    method, _url, _headers, _data = t.calls[-1]
    assert method == "POST"


def test_delete_card_forwards_if_match() -> None:
    book, t = make_book()
    book.delete_card("/book/a.vcf", if_match='"1"')
    method, _url, headers, _data = t.calls[-1]
    assert method == "DELETE"
    assert headers["If-Match"] == '"1"'


def test_export_bundle_contains_all_cards(tmp_path: Path) -> None:
    book, _t = make_book()
    out = book.export(tmp_path / "out.vcf")
    content = Path(out).read_bytes()
    assert b"UID:a" in content and b"UID:b" in content


def test_export_per_card_writes_one_file_each(tmp_path: Path) -> None:
    book, _t = make_book()
    out = book.export(tmp_path / "dir", per_card=True)
    assert (out / "a.vcf").exists() and (out / "b.vcf").exists()


def test_raise_for_status_wiring() -> None:
    # sanity: PreconditionFailed / DAVError are importable and in the hierarchy
    assert issubclass(PreconditionFailed, DAVError)
