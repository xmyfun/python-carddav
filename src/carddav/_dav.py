"""DAV primitives: build requests, map status codes to exceptions.

This module is deliberately stateless - it turns an HTTP exchange into either
parsed XML/bytes or a typed exception. No cross-request state machine lives
here (incremental sync state is the caller's job).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from . import _xml
from ._http import Response
from ._transport import Transport
from .errors import (
    AuthenticationError,
    Conflict,
    DAVError,
    DiscoveryError,
    InsufficientStorage,
    MissingUIDError,
    NotFound,
    PermissionDenied,
    PreconditionFailed,
    SyncTokenInvalid,
)

XML_CT = "application/xml; charset=utf-8"


def _snippet(resp: Response, n: int = 80) -> str:
    return resp.content[:n].decode("utf-8", errors="replace")


def _mentions_uid(resp: Response) -> bool:
    return "uid" in resp.text.lower()


def _mentions_sync_token(resp: Response) -> bool:
    return "valid-sync-token" in resp.text.lower()


def raise_for_status(resp: Response, *, method: str, href: str | None = None) -> None:
    """Translate a non-2xx response into a typed :class:`DAVError`."""
    code = resp.status_code
    if 200 <= code < 300:
        return
    common: dict[str, Any] = {
        "status": code,
        "method": method,
        "href": href,
        "snippet": _snippet(resp),
    }
    if code == 401:
        raise AuthenticationError("authentication failed", **common)
    if code == 403:
        if _mentions_sync_token(resp):
            raise SyncTokenInvalid("sync token rejected or expired", **common)
        raise PermissionDenied("forbidden", **common)
    if code == 404:
        raise NotFound("resource not found", **common)
    if code == 409:
        raise Conflict("conflict", **common)
    if code == 412:
        raise PreconditionFailed("precondition failed (ETag mismatch)", **common)
    if code == 507:
        raise InsufficientStorage("insufficient storage", **common)
    if code == 400 and _mentions_uid(resp):
        raise MissingUIDError("server rejected the card for a missing UID", **common)
    raise DAVError(f"unexpected status {code}", **common)


def request(
    transport: Transport,
    method: str,
    url: str,
    *,
    depth: str | None = None,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Send a DAV request with the usual headers; maps errors to exceptions."""
    hdrs = dict(headers) if headers else {}
    if depth is not None:
        hdrs["Depth"] = depth
    data = body.encode("utf-8") if body is not None else None
    if data is not None:
        hdrs.setdefault("Content-Type", XML_CT)
    resp = transport.request(method, url, headers=hdrs, content=data)
    raise_for_status(resp, method=method, href=url)
    return resp


def propfind(transport: Transport, url: str, body: str, *, depth: str) -> ET.Element:
    resp = request(transport, "PROPFIND", url, depth=depth, body=body)
    return _xml.parse_multistatus(resp.content)


def report(transport: Transport, url: str, body: str, *, depth: str = "0") -> ET.Element:
    resp = request(transport, "REPORT", url, depth=depth, body=body)
    return _xml.parse_multistatus(resp.content)


def get_bytes(transport: Transport, url: str) -> tuple[bytes, str | None]:
    """GET one resource; returns ``(content, etag)``.

    The ETag comes from the response header, so a card fetched this way can be
    updated safely with ``If-Match`` without an extra PROPFIND
    (RFC 6352 section 6.3.2.3: the entity tag is the resource's ETag).
    """
    resp = request(transport, "GET", url)
    content_type = resp.headers.get("Content-Type") or ""
    if "html" in content_type.lower():
        raise DiscoveryError(
            f"GET returned HTML, not a vCard (Content-Type: {content_type})",
            href=url,
            snippet=_snippet(resp),
        )
    return resp.content, resp.headers.get("ETag")
