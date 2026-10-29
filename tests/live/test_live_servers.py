"""Live tests against real CardDAV servers: discovery/read, write round-trip, and
``sync-collection`` incrementals.

Credentials are read from ``tests/live/servers.ini`` (gitignored) — never from
source, environment, logs, or the chat. A server section that is absent or has
an empty username is skipped.

Run::

    uv run pytest -m live
"""

from __future__ import annotations

import configparser
import os
import tempfile
import uuid
from pathlib import Path

import pytest

from carddav import BearerAuth, DAVError, PreconditionFailed, SyncTokenInvalid, get_davclient

pytestmark = pytest.mark.live

_CONFIG = Path(__file__).with_name("servers.ini")

# One section per CardDAV server; the read-only smoke test runs against every
# section that is configured in servers.ini.
_SERVERS = (
    "disroot",
    "google_people",
    "icloud",
    "synology_contacts",
)


def _load() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    if _CONFIG.exists():
        parser.read(_CONFIG)
    return parser


def _creds(section: str) -> tuple[str, str, str, str, bool] | None:
    """Return (url, username, password, auth, verify) or None if unconfigured."""
    parser = _load()
    if not parser.has_section(section):
        return None
    url = parser.get(section, "url", fallback="").strip()
    username = parser.get(section, "username", fallback="").strip()
    password = parser.get(section, "password", fallback="").strip()
    if not url or not username:
        return None
    auth = parser.get(section, "auth", fallback="basic").strip().lower()
    verify = parser.getboolean(section, "verify", fallback=True)
    return url, username, password, auth, verify


@pytest.mark.parametrize("section", _SERVERS)
def test_discover_list_and_read(section: str) -> None:
    creds = _creds(section)
    if creds is None:
        pytest.skip(f"[{section}] not configured in tests/live/servers.ini")

    url, username, password, auth_type, verify = creds

    from carddav import BearerAuth, get_davclient

    auth = BearerAuth(password) if auth_type == "bearer" else None
    with get_davclient(
        url,
        username=None if auth else username,
        password=None if auth else password,
        auth=auth,
        verify=verify,
    ) as client:
        books = client.get_addressbooks()
        assert isinstance(books, list)
        if not books:
            pytest.skip(f"[{section}] no addressbooks discovered")
        book = books[0]
        cards = book.get_cards()
        assert isinstance(cards, list)
        if cards:
            first = book.get_card(cards[0].href)
            assert isinstance(first.data, bytes) and first.data


def test_synology_write_read_update_delete() -> None:
    """Full write-path smoke test against Synology Contacts (Radicale).

    Creates via PUT (the working path on this Radicale build), reads back,
    batch-reads via multiget, updates via PUT+If-Match, checks the 412 conflict
    path, exports, and cleans up all created cards. POST create is asserted to
    raise (this Synology Radicale returns 500 on POST — a documented quirk).
    """
    creds = _creds("synology_contacts")
    if creds is None:
        pytest.skip("[synology_contacts] not configured in tests/live/servers.ini")

    url, username, password, auth_type, verify = creds
    auth = BearerAuth(password) if auth_type == "bearer" else None

    prefix = f"carddav-lib-test-{uuid.uuid4().hex[:8]}"
    uid_a = f"{prefix}-a"

    def vcard(uid: str, fn: str) -> bytes:
        return (
            "BEGIN:VCARD\r\nVERSION:3.0\r\n"
            f"UID:{uid}\r\n"
            f"FN:{fn}\r\n"
            "N:Test;CardDAV Lib Write;;;\r\n"
            "END:VCARD\r\n"
        ).encode()

    with get_davclient(
        url,
        username=None if auth else username,
        password=None if auth else password,
        auth=auth,
        verify=verify,
    ) as client:
        books = client.get_addressbooks()
        if not books:
            pytest.skip("[synology_contacts] no addressbooks discovered")
        book = books[0]

        def href_of(uid: str) -> str:
            for c in book.get_all_cards():
                if c.uid == uid:
                    return c.href
            raise AssertionError(f"card {uid} not found after create")

        try:
            # 1) create via PUT (UID-derived URL) — standard RFC 6352 create path
            etag_a = book.put_card(vcard(uid_a, "Put Create"), create_only=True)
            assert etag_a
            href_a = href_of(uid_a)
            # 2) read back
            card = book.get_card(href_a)
            assert card.uid == uid_a, card.uid
            # 3) POST create is unsupported on this Synology Radicale build (500)
            with pytest.raises(DAVError):
                book.post_card(vcard(f"{prefix}-post", "Post Create"))
            # 4) batch read via multiget
            assert uid_a in {c.uid for c in book.get_all_cards()}
            # 5) update via PUT + If-Match
            new_etag = book.put_card(vcard(uid_a, "Put Create (edited)"), if_match=card.etag)
            assert new_etag and new_etag != card.etag
            edited = book.get_card(href_a)
            assert b"(edited)" in edited.data
            # 6) 412 conflict on a wrong If-Match
            with pytest.raises(PreconditionFailed):
                book.put_card(vcard(uid_a, "conflict"), if_match='"nope-not-an-etag"')
            # 7) export bundle
            with tempfile.TemporaryDirectory() as d:
                out = book.export(os.path.join(d, "export.vcf"))
                assert uid_a.encode() in Path(out).read_bytes()
        finally:
            # robust cleanup: delete anything we created, by uid prefix
            for c in book.get_all_cards():
                if (c.uid or "").startswith(prefix):
                    try:
                        book.delete_card(c.href)
                    except DAVError:
                        pass


def _change_for(changes: list, uid: str):  # noqa: ANN201 - tiny local helper
    """The change entry for ``<uid>.vcf`` (resource name == uid on this server)."""
    return next((c for c in changes if c.href.endswith(f"{uid}.vcf")), None)


def test_synology_sync_collection_roundtrip() -> None:
    """``sync-collection`` incremental round-trip: create / update / delete / idle.

    Verified against Synology Contacts (Radicale) on 2026-10-29:
    each write yields exactly one change, the token advances per change, a delete
    is reported with a ``404`` status and no etag, and an idle poll returns no
    entries.

    Also pins down a quirk of this build: an **unknown token does not** produce
    ``403 valid-sync-token`` (RFC 6578 §3.2) — it silently returns a full listing
    plus the current token. So the test accepts either shape; what matters is
    that the library surfaces one of them instead of crashing.
    """
    creds = _creds("synology_contacts")
    if creds is None:
        pytest.skip("[synology_contacts] not configured in tests/live/servers.ini")

    url, username, password, auth_type, verify = creds
    auth = BearerAuth(password) if auth_type == "bearer" else None

    prefix = f"carddav-sync-test-{uuid.uuid4().hex[:8]}"
    uid = f"{prefix}-a"

    def vcard(fn: str) -> bytes:
        return (
            "BEGIN:VCARD\r\nVERSION:3.0\r\n"
            f"UID:{uid}\r\n"
            f"FN:{fn}\r\n"
            "N:Sync;Test;;;\r\n"
            "END:VCARD\r\n"
        ).encode()

    with get_davclient(
        url,
        username=None if auth else username,
        password=None if auth else password,
        auth=auth,
        verify=verify,
    ) as client:
        books = client.get_addressbooks()
        if not books:
            pytest.skip("[synology_contacts] no addressbooks discovered")
        book = books[0]

        try:
            # 0) initial full sync: no token in, a token out
            _initial, token0 = book.get_changes(None)
            assert token0

            # 1) create → exactly one change for our card, carrying an etag
            book.put_card(vcard("Sync A"), create_only=True)
            changes, token1 = book.get_changes(token0)
            item = _change_for(changes, uid)
            assert item is not None and not item.deleted, changes
            assert item.etag

            # 2) update → same href, new etag
            card = book.get_card(item.href)
            assert card.uid == uid
            book.put_card(vcard("Sync A (edited)"), href=card.href, if_match=card.etag)
            changes, token2 = book.get_changes(token1)
            updated = _change_for(changes, uid)
            assert updated is not None and not updated.deleted, changes
            assert updated.etag and updated.etag != item.etag

            # 3) delete → reported as deleted (404 status), no etag
            book.delete_card(updated.href)
            changes, token3 = book.get_changes(token2)
            gone = _change_for(changes, uid)
            assert gone is not None and gone.deleted, changes
            assert gone.etag is None

            # 4) idle poll → no entry for our card, a token still comes back
            changes, token4 = book.get_changes(token3)
            assert _change_for(changes, uid) is None
            assert token4

            # 5) unknown token → RFC 6578 403 OR a silent full listing
            try:
                _changes, fallback_token = book.get_changes(
                    "urn:uuid:00000000-0000-0000-0000-000000000000"
                )
            except SyncTokenInvalid:
                pass
            else:
                assert fallback_token
        finally:
            for c in book.get_all_cards():
                if (c.uid or "").startswith(prefix):
                    try:
                        book.delete_card(c.href)
                    except DAVError:
                        pass


def test_synology_uid_is_taken_from_the_resource_name() -> None:
    """Q11: on Radicale the **URL is the identity authority**, not the vCard UID.

    1) PUT a card with *no* UID at an explicit href → the server inserts
       ``UID:<file stem>`` (measured 2026-10-29).
    2) PUT a card whose UID differs from the file stem → the server **rewrites**
       the UID to the stem; no second resource appears.
    """
    creds = _creds("synology_contacts")
    if creds is None:
        pytest.skip("[synology_contacts] not configured in tests/live/servers.ini")

    url, username, password, auth_type, verify = creds
    auth = BearerAuth(password) if auth_type == "bearer" else None

    prefix = f"carddav-uid-test-{uuid.uuid4().hex[:8]}"
    stem = f"{prefix}-alpha"

    with get_davclient(
        url,
        username=None if auth else username,
        password=None if auth else password,
        auth=auth,
        verify=verify,
    ) as client:
        books = client.get_addressbooks()
        if not books:
            pytest.skip("[synology_contacts] no addressbooks discovered")
        book = books[0]

        try:
            # 1) no UID in the body → server fills it from the file name
            book.put_card(
                b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:No UID Probe\r\nEND:VCARD\r\n",
                href=f"{stem}.vcf",
            )
            card = book.get_card(f"{stem}.vcf")
            assert card.uid == stem, card.uid

            # 2) conflicting UID → server rewrites it to the file name
            book.put_card(
                b"BEGIN:VCARD\r\nVERSION:3.0\r\n"
                b"UID:some-other-uid\r\nFN:Rewrite Probe\r\nEND:VCARD\r\n",
                href=f"{stem}.vcf",
                if_match=card.etag,
            )
            rewritten = book.get_card(f"{stem}.vcf")
            assert rewritten.uid == stem, rewritten.uid
            same_prefix = [c.href for c in book.get_cards() if prefix in c.href]
            assert len(same_prefix) == 1, same_prefix
        finally:
            for c in book.get_cards():
                if prefix in c.href:
                    try:
                        book.delete_card(c.href)
                    except DAVError:
                        pass


_QUERY_TMPL = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:getetag/><c:address-data/></d:prop>"
    "<c:filter><c:prop-filter name=\"FN\">"
    "<c:text-match>{needle}</c:text-match>"
    "</c:prop-filter></c:filter>"
    "</c:addressbook-query>"
)


def test_synology_addressbook_query_text_match() -> None:
    """``addressbook-query`` (RFC 6352 §8.6) with a ``text-match`` on ``FN``.

    The body is passed through verbatim, so this also proves the server accepts
    the XML we hand it (Radicale supports ``text-match``; it **ignores**
    ``CARDDAV:limit`` — measured 2026-10-29, see ``internal/06`` Q10).
    """
    creds = _creds("synology_contacts")
    if creds is None:
        pytest.skip("[synology_contacts] not configured in tests/live/servers.ini")

    url, username, password, auth_type, verify = creds
    auth = BearerAuth(password) if auth_type == "bearer" else None

    prefix = f"carddav-query-test-{uuid.uuid4().hex[:8]}"
    uid_a, uid_b = f"{prefix}-a", f"{prefix}-b"

    def vcard(uid: str, fn: str) -> bytes:
        return (
            "BEGIN:VCARD\r\nVERSION:3.0\r\n"
            f"UID:{uid}\r\n"
            f"FN:{fn}\r\n"
            "N:Query;Test;;;\r\n"
            "END:VCARD\r\n"
        ).encode()

    with get_davclient(
        url,
        username=None if auth else username,
        password=None if auth else password,
        auth=auth,
        verify=verify,
    ) as client:
        books = client.get_addressbooks()
        if not books:
            pytest.skip("[synology_contacts] no addressbooks discovered")
        book = books[0]

        try:
            book.put_card(vcard(uid_a, f"Query Alpha {prefix}"), create_only=True)
            book.put_card(vcard(uid_b, f"Query Beta {prefix}"), create_only=True)

            # both match the shared prefix...
            cards = book.search(_QUERY_TMPL.format(needle=prefix))
            assert {c.uid for c in cards} == {uid_a, uid_b}
            assert all(c.data and b"BEGIN:VCARD" in c.data for c in cards)

            # ...and only one matches "Alpha"
            cards = book.search(_QUERY_TMPL.format(needle="Alpha"))
            assert [c.uid for c in cards] == [uid_a]
        finally:
            for c in book.get_all_cards():
                if (c.uid or "").startswith(prefix):
                    try:
                        book.delete_card(c.href)
                    except DAVError:
                        pass
