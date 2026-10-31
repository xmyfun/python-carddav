"""requests backend - optional, kept so the HTTP stack can be swapped.

Install with ``pip install 'carddav[requests]'`` and pass ``backend="requests"``.
It reproduces the same response shape and error mapping as the default backend.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from ._http import DEFAULT_TIMEOUT, USER_AGENT, Headers, Response
from .auth import BasicAuth, BearerAuth, DigestAuth
from .errors import TransportError


class RequestsBackend:
    """One ``requests.Session`` per CardDAV connection."""

    name = "requests"

    def __init__(
        self,
        *,
        auth: object | None = None,
        verify: bool = True,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        trust_env: bool = True,
    ) -> None:
        self._session = requests.Session()
        self._session.trust_env = trust_env
        native, extra_headers = _translate_auth(auth)
        if native is not None:
            self._session.auth = native
        self._session.headers.update({"User-Agent": USER_AGENT, **extra_headers})
        self._timeout = timeout
        self._verify = verify

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        follow_redirects: bool = True,
    ) -> Response:
        try:
            r = self._session.request(
                method,
                url,
                headers=dict(headers) if headers else None,
                data=content,
                timeout=self._timeout,
                verify=self._verify,
                allow_redirects=follow_redirects,
            )
        except requests.RequestException as exc:
            raise TransportError(f"{method} {url} failed") from exc
        return Response(
            status_code=r.status_code,
            content=r.content,
            text=r.text,
            headers=Headers(list(r.headers.items())),
            url=r.url,
            history=tuple(h.url for h in r.history),
        )

    def close(self) -> None:
        self._session.close()


def _translate_auth(auth: object | None) -> tuple[Any, dict[str, str]]:
    """Map our auth objects to requests ones; pass backend-native objects through."""
    if auth is None:
        return None, {}
    if isinstance(auth, BearerAuth):
        return None, {"Authorization": f"Bearer {auth.token}"}
    if isinstance(auth, BasicAuth):
        return requests.auth.HTTPBasicAuth(auth.username, auth.password), {}
    if isinstance(auth, DigestAuth):
        return requests.auth.HTTPDigestAuth(auth.username, auth.password), {}
    return auth, {}  # already a requests AuthBase
