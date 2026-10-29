"""Authentication objects for the carddav library.

These are **plain value objects**, not tied to any HTTP library: the chosen
backend translates them into whatever its client expects (``httpx.BasicAuth``,
``requests.auth.HTTPBasicAuth``, an ``Authorization`` header, ...). That keeps
the public API stable when the transport changes.

Only the transport-level credential is modelled here: the OAuth2
authorization-code flow and token refresh deliberately live *outside* this
library (same split as ``caldav``, see ``internal/02`` section 11). A backend-native auth
object (e.g. ``httpx.DigestAuth``) may also be passed straight through.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasicAuth:
    """Username / password over HTTP Basic."""

    username: str
    password: str


@dataclass(frozen=True)
class DigestAuth:
    """Username / password over HTTP Digest (the backend performs the handshake)."""

    username: str
    password: str


@dataclass(frozen=True)
class BearerAuth:
    """A pre-obtained OAuth2 access token, sent as ``Authorization: Bearer``."""

    token: str

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("BearerAuth requires a non-empty token")


AuthLike = BasicAuth | DigestAuth | BearerAuth

__all__ = ["BasicAuth", "DigestAuth", "BearerAuth", "AuthLike"]
