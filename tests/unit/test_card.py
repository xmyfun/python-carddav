"""Tests for the minimal UID extraction (the only vCard parsing this library does)."""

from __future__ import annotations

from urllib.parse import unquote

from carddav.card import extract_uid, uid_to_resource_name


def test_extract_uid_plain() -> None:
    assert extract_uid(b"BEGIN:VCARD\nUID:urn:uuid:abc\nEND:VCARD\n") == "urn:uuid:abc"


def test_extract_uid_unfolds_continuation() -> None:
    assert extract_uid(b"UID:urn:uuid:abc\n def\nFN:X\n") == "urn:uuid:abcdef"


def test_extract_uid_missing() -> None:
    assert extract_uid(b"BEGIN:VCARD\nFN:X\nEND:VCARD\n") is None


def test_extract_uid_with_params() -> None:
    assert extract_uid(b"UID;X-ABUID=1:123\n") == "123"


def test_resource_name_encodes_path_separators() -> None:
    """A crafted UID must stay one segment - no literal separator survives."""
    name = uid_to_resource_name("../../evil")
    assert name == "..%2F..%2Fevil"
    assert "/" not in name
    assert uid_to_resource_name("a/b/c") == "a%2Fb%2Fc"


def test_resource_name_encodes_scheme_colons() -> None:
    """``urn:uuid:...`` would be parsed as a URI scheme and leave the HTTP URL."""
    assert uid_to_resource_name("urn:uuid:abc") == "urn%3Auuid%3Aabc"


def test_resource_name_is_reversible() -> None:
    """Encoding keeps the UID recoverable - that is why we encode, not strip."""
    for uid in ("urn:uuid:abc", "a/b/c", "../../evil", "张三", "a b"):
        assert unquote(uid_to_resource_name(uid) or "") == uid


def test_resource_name_leaves_plain_uids_alone() -> None:
    """Normal UUIDs must be unchanged, so hrefs derived today stay stable."""
    uid = "3f2a1b4c-5d6e-7f80-9a1b-2c3d4e5f6a7b"
    assert uid_to_resource_name(uid) == uid


def test_resource_name_rejects_empty_uid() -> None:
    assert uid_to_resource_name("") is None
    assert uid_to_resource_name("   ") is None
