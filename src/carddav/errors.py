"""Exception hierarchy for the carddav library.

Public API - every exception raised by this library is a subclass of
:class:`DAVError`. Requests/urllib3 exceptions are never leaked directly;
they are wrapped in :class:`TransportError` (with ``raise ... from exc``).

The full list and trigger conditions are documented in ``internal/02`` section 8.
"""

from __future__ import annotations


class DAVError(Exception):
    """Base class for all carddav errors.

    Carries the HTTP context (status/method/href) and a truncated response
    snippet for diagnostics. Credentials must never appear here.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        method: str | None = None,
        href: str | None = None,
        snippet: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.method = method
        self.href = href
        self.snippet = snippet

    def __str__(self) -> str:  # noqa: D105 - overriding builtin
        parts = [self.message]
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.method is not None:
            parts.append(f"method={self.method}")
        if self.href is not None:
            parts.append(f"href={self.href!r}")
        return " ".join(parts)


class AuthenticationError(DAVError):
    """HTTP 401 - credentials rejected (e.g. iCloud app-specific password)."""


class PermissionDenied(DAVError):
    """HTTP 403 - authenticated but not allowed on this resource."""


class NotFound(DAVError):
    """HTTP 404 - resource (or href) does not exist."""


class Conflict(DAVError):
    """HTTP 409 - generic conflict."""


class PreconditionFailed(DAVError):
    """HTTP 412 - ``If-Match``/``If-None-Match`` precondition failed.

    ``snippet`` carries the server's current ETag when it was returned.
    """


class InsufficientStorage(DAVError):
    """HTTP 507 - server quota exceeded."""


class SyncTokenInvalid(DAVError):
    """The sync token was rejected/expired; the caller must fall back to a full sync."""


class MissingUIDError(DAVError):
    """Server answered 400 and the error body points at a missing UID.

    Raised only when the server rejects the card; the library never pre-checks
    UID client-side (see ``internal/02`` section 6).
    """


class UnsafeXML(DAVError):
    """Response contained a DOCTYPE (entity-expansion risk) and was rejected."""


class DiscoveryError(DAVError):
    """The URL did not yield a DAV response (HTML login page, 502, ...)."""


class TransportError(DAVError):
    """A network/timeout error occurred; the original exception is chained."""
