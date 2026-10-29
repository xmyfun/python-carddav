"""Byte-level assertions for the XML request templates and the DOCTYPE guard."""

from __future__ import annotations

import pytest

from carddav import _xml
from carddav.errors import DiscoveryError, UnsafeXML


def test_propfind_current_user_principal_exact_bytes() -> None:
    expected = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:"><d:prop>'
        "<d:current-user-principal/><d:resourcetype/>"
        "</d:prop></d:propfind>"
    )
    assert _xml.propfind_current_user_principal() == expected


def test_report_multiget_escapes_href() -> None:
    body = _xml.report_multiget(["a&b.vcf", "x<y>.vcf"])
    assert "a&amp;b.vcf" in body
    assert "a&b.vcf" not in body
    assert "x&lt;y&gt;.vcf" in body


def test_report_sync_collection_no_token_omits_element() -> None:
    body = _xml.report_sync_collection(None)
    assert "sync-token" not in body
    body2 = _xml.report_sync_collection("http://sabre.io/ns/sync/42")
    assert "<d:sync-token>http://sabre.io/ns/sync/42</d:sync-token>" in body2


def test_reject_doctype_rejects_declaration() -> None:
    with pytest.raises(UnsafeXML):
        _xml.reject_doctype(b'<?xml version="1.0"?><!DOCTYPE foo [ <!ENTITY a "AAAA"> ]><x/>')


def test_reject_doctype_rejects_utf16_bypass() -> None:
    # A UTF-16 payload hides "<!DOCTYPE" from a naive byte substring check;
    # strict UTF-8 decoding must reject it.
    payload = (
        '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE foo [<!ENTITY a "AAAA">]><x/>'.encode(
            "utf-16"
        )
    )
    with pytest.raises(UnsafeXML):
        _xml.reject_doctype(payload)


def test_reject_doctype_passes_clean_xml() -> None:
    payload = b'<?xml version="1.0"?><x/>'
    assert _xml.reject_doctype(payload) == payload


def test_parse_multistatus_rejects_html() -> None:
    # Well-formed XML but not a DAV multistatus (e.g. a login page without DOCTYPE).
    with pytest.raises(DiscoveryError):
        _xml.parse_multistatus(b"<html><body>login</body></html>")


def test_parse_multistatus_and_helpers() -> None:
    body = (
        b'<?xml version="1.0"?>'
        b'<d:multistatus xmlns:d="DAV:">'
        b"<d:response><d:href>/x.vcf</d:href>"
        b'<d:propstat><d:prop><d:getetag>"e"</d:getetag></d:prop></d:propstat>'
        b"</d:response>"
        b"</d:multistatus>"
    )
    root = _xml.parse_multistatus(body)
    responses = _xml.iter_responses(root)
    assert len(responses) == 1
    assert _xml.response_href(responses[0]) == "/x.vcf"
    assert _xml.find_text(responses[0], _xml.DAV_NS, "getetag") == '"e"'
