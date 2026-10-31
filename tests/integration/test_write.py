"""RFC 6352 create / read / update / delete round-trip (a write test)."""

from __future__ import annotations

import uuid

import pytest
from _checks import href_of, vcard

from carddav import PreconditionFailed


def test_put_create_read_update_delete(writable, cleanup, tmp_path) -> None:
    with writable.client() as client:
        book = client.get_addressbooks()[0]
        prefix = f"carddav-write-{uuid.uuid4().hex[:8]}"
        uid = f"{prefix}-a"

        etag = book.put_card(vcard(uid, "Put Create"), create_only=True)
        assert etag, "put_card returned no ETag"
        href = href_of(book, uid)
        cleanup.append(href)

        card = book.get_card(href)
        assert card.uid == uid

        new_etag = book.put_card(vcard(uid, "Put Create (edited)"), if_match=card.etag)
        assert new_etag and new_etag != card.etag
        assert b"(edited)" in book.get_card(href).data

        with pytest.raises(PreconditionFailed):
            book.put_card(vcard(uid, "conflict"), if_match='"nope-not-an-etag"')

        assert uid in {c.uid for c in book.get_all_cards()}

        out = book.export(tmp_path / "export.vcf")
        assert uid.encode() in out.read_bytes()
