"""RFC 6352 ``addressbook-query`` with a ``text-match`` on ``FN`` (a write test)."""

from __future__ import annotations

import uuid

from _checks import href_of, vcard

_QUERY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:getetag/><c:address-data/></d:prop>"
    '<c:filter><c:prop-filter name="FN">'
    "<c:text-match>{needle}</c:text-match>"
    "</c:prop-filter></c:filter>"
    "</c:addressbook-query>"
)


def test_addressbook_query_text_match(writable, cleanup) -> None:
    with writable.client() as client:
        book = client.get_addressbooks()[0]
        prefix = f"carddav-query-{uuid.uuid4().hex[:8]}"
        uid_a, uid_b = f"{prefix}-a", f"{prefix}-b"

        book.put_card(vcard(uid_a, f"Query Alpha {prefix}"), create_only=True)
        book.put_card(vcard(uid_b, f"Query Beta {prefix}"), create_only=True)
        cleanup.extend([href_of(book, uid_a), href_of(book, uid_b)])

        cards = book.search(_QUERY.format(needle=prefix))
        assert {c.uid for c in cards} == {uid_a, uid_b}
        assert all(c.data and b"BEGIN:VCARD" in c.data for c in cards)

        cards = book.search(_QUERY.format(needle="Alpha"))
        assert [c.uid for c in cards] == [uid_a]
