"""RFC 6578 ``sync-collection`` round-trip (a write test)."""

from __future__ import annotations

import uuid

import pytest
from _checks import href_of, vcard

from carddav import DAVError


def _change_for(changes, uid: str):
    return next((c for c in changes if c.href.endswith(f"{uid}.vcf")), None)


def test_sync_collection_roundtrip(writable, cleanup) -> None:
    with writable.client() as client:
        book = client.get_addressbooks()[0]
        prefix = f"carddav-sync-{uuid.uuid4().hex[:8]}"
        uid = f"{prefix}-a"

        try:
            _initial, token0 = book.get_changes(None)
        except DAVError:
            pytest.skip("sync-collection is not supported by this server")
        assert token0

        book.put_card(vcard(uid, "Sync A"), create_only=True)
        cleanup.append(href_of(book, uid))
        changes, token1 = book.get_changes(token0)
        item = _change_for(changes, uid)
        assert item is not None and not item.deleted, changes
        assert item.etag

        card = book.get_card(item.href)
        assert card.uid == uid
        book.put_card(vcard(uid, "Sync A (edited)"), href=card.href, if_match=card.etag)
        changes, token2 = book.get_changes(token1)
        updated = _change_for(changes, uid)
        assert updated is not None and not updated.deleted, changes
        assert updated.etag and updated.etag != item.etag

        book.delete_card(updated.href)
        changes, token3 = book.get_changes(token2)
        gone = _change_for(changes, uid)
        assert gone is not None and gone.deleted, changes
        assert gone.etag is None

        changes, token4 = book.get_changes(token3)
        assert _change_for(changes, uid) is None
        assert token4
