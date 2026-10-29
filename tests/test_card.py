"""Tests for the minimal UID extraction (the only vCard parsing this library does)."""

from __future__ import annotations

from carddav.card import extract_uid


def test_extract_uid_plain() -> None:
    assert extract_uid(b"BEGIN:VCARD\nUID:urn:uuid:abc\nEND:VCARD\n") == "urn:uuid:abc"


def test_extract_uid_unfolds_continuation() -> None:
    assert extract_uid(b"UID:urn:uuid:abc\n def\nFN:X\n") == "urn:uuid:abcdef"


def test_extract_uid_missing() -> None:
    assert extract_uid(b"BEGIN:VCARD\nFN:X\nEND:VCARD\n") is None


def test_extract_uid_with_params() -> None:
    assert extract_uid(b"UID;X-ABUID=1:123\n") == "123"
