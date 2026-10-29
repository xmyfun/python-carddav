"""XML request templates, DOCTYPE guard, and namespace-aware helpers.

The request bodies are built from **string templates on purpose**: the tests
must be able to assert the exact bytes we send (see ``internal/02`` section 2). Using an
XML serializer would let prefix/attribute order vary and make byte-level
assertions brittle.

All responses are parsed with the standard library ``ElementTree``, matching on
``{namespace}localname`` (prefix-agnostic). Any payload carrying a ``DOCTYPE``
is rejected before parsing (entity-expansion guard); only UTF-8 is accepted, so
a UTF-16 encoded payload fails at decode time rather than slipping past a naive
byte substring check.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .errors import DiscoveryError, UnsafeXML

DAV_NS = "DAV:"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"
CS_NS = "http://calendarserver.org/ns/"


def _q(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def escape_xml(text: str) -> str:
    """Escape text for use inside an XML element (attributes not supported)."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


# ---- request templates -----------------------------------------------------


def propfind_current_user_principal() -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:"><d:prop>'
        "<d:current-user-principal/><d:resourcetype/>"
        "</d:prop></d:propfind>"
    )


def propfind_discovery() -> str:
    """Combined Depth:0 probe: principal / home-set / resourcetype / displayname."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav"><d:prop>'
        "<d:current-user-principal/><d:resourcetype/><d:displayname/><c:addressbook-home-set/>"
        "</d:prop></d:propfind>"
    )


def propfind_resourcetype() -> str:
    """Minimal Depth:0 probe (works on collections without a principal)."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav"><d:prop>'
        "<d:resourcetype/><d:displayname/>"
        "</d:prop></d:propfind>"
    )


def propfind_addressbook_home_set() -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav"><d:prop>'
        "<d:displayname/><d:resourcetype/><c:addressbook-home-set/>"
        "</d:prop></d:propfind>"
    )


def propfind_addressbooks() -> str:
    """PROPFIND Depth:1 body enumerating addressbook collections under home-set."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav" '
        'xmlns:cs="http://calendarserver.org/ns/"><d:prop>'
        "<d:displayname/><d:resourcetype/><cs:getctag/>"
        "</d:prop></d:propfind>"
    )


def propfind_cards() -> str:
    """PROPFIND Depth:1 body listing a collection's members (href/etag/vCard)."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav"><d:prop>'
        "<d:getetag/><d:resourcetype/><c:address-data/>"
        "</d:prop></d:propfind>"
    )


def report_multiget(hrefs: list[str]) -> str:
    hrefs_xml = "".join(f"<d:href>{escape_xml(h)}</d:href>" for h in hrefs)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<c:addressbook-multiget xmlns:d="DAV:" '
        'xmlns:c="urn:ietf:params:xml:ns:carddav">'
        "<d:prop><d:getetag/><c:address-data/></d:prop>" + hrefs_xml + "</c:addressbook-multiget>"
    )


def report_sync_collection(sync_token: str | None) -> str:
    token_xml = (
        "" if sync_token is None else f"<d:sync-token>{escape_xml(sync_token)}</d:sync-token>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:sync-collection xmlns:d="DAV:">' + token_xml + "<d:sync-level>1</d:sync-level>"
        "<d:prop><d:getetag/></d:prop>"
        "</d:sync-collection>"
    )


# ---- response handling -----------------------------------------------------


def reject_doctype(payload: bytes) -> bytes:
    """Strict UTF-8 decode, then reject any DOCTYPE. Returns the bytes unchanged."""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsafeXML("response is not valid UTF-8; refusing to parse") from exc
    if "<!doctype" in text.lower():
        raise UnsafeXML("response contains a DOCTYPE (entity expansion risk)")
    return payload


def parse_multistatus(payload: bytes) -> ET.Element:
    """Decode-guard + parse a DAV ``multistatus``; raises DiscoveryError if not DAV."""
    reject_doctype(payload)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise DiscoveryError("response is not well-formed XML") from exc
    if root.tag != _q(DAV_NS, "multistatus"):
        raise DiscoveryError(
            f"expected a DAV multistatus, got {root.tag!r}",
            snippet=payload[:80].decode("utf-8", errors="replace"),
        )
    return root


def find_text(element: ET.Element, ns: str, local: str) -> str | None:
    """First (depth-first) text of ``{ns}local`` under *element*, or None."""
    node = element.find(f".//{_q(ns, local)}")
    return node.text if node is not None else None


def iter_responses(root: ET.Element) -> list[ET.Element]:
    """Return the ``<d:response>`` children of a multistatus root."""
    return list(root.findall(_q(DAV_NS, "response")))


def response_href(resp: ET.Element) -> str | None:
    return find_text(resp, DAV_NS, "href")


def response_has(resp: ET.Element, ns: str, local: str) -> bool:
    return resp.find(f".//{_q(ns, local)}") is not None


def find_child_href(element: ET.Element, ns: str, local: str) -> str | None:
    """Text of the ``<d:href>`` inside the first ``{ns}local`` element."""
    node = element.find(f".//{_q(ns, local)}")
    if node is None:
        return None
    href = node.find(_q(DAV_NS, "href"))
    return href.text if href is not None else None
