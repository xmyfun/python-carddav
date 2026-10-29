"""httpx backend - the default HTTP stack (HTTP/1.1, HTTP/2, HTTP/3-ready)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ._http import DEFAULT_TIMEOUT, USER_AGENT, Headers, Response
from .auth import BasicAuth, BearerAuth, DigestAuth
from .errors import TransportError


class HttpxBackend:
    """One ``httpx.Client`` per CardDAV connection."""

    name = "httpx"

    def __init__(
        self,
        *,
        auth: object | None = None,
        verify: bool = True,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        http2: bool = False,
    ) -> None:
        native, extra_headers = _translate_auth(auth)
        try:
            self._client = httpx.Client(
                auth=native,
                verify=verify,
                timeout=httpx.Timeout(
                    connect=timeout[0], read=timeout[1], write=timeout[1], pool=timeout[0]
                ),
                http2=http2,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, **extra_headers},
            )
        except ImportError as exc:  # pragma: no cover - depends on optional h2 install
            raise ImportError(
                "http2=True needs the optional dependency: pip install 'carddav[http2]'"
            ) from exc

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
            r = self._client.request(
                method,
                url,
                headers=headers,
                content=content,
                follow_redirects=follow_redirects,
            )
        except httpx.HTTPError as exc:
            raise TransportError(f"{method} {url} failed") from exc
        return Response(
            status_code=r.status_code,
            content=r.content,
            text=r.text,
            headers=Headers(list(r.headers.items())),
            url=str(r.url),
            history=tuple(str(h.url) for h in r.history),
        )

    def close(self) -> None:
        self._client.close()


def _translate_auth(auth: object | None) -> tuple[Any, dict[str, str]]:
    """Map our auth objects to httpx ones; pass backend-native objects through."""
    if auth is None:
        return None, {}
    if isinstance(auth, BearerAuth):
        return None, {"Authorization": f"Bearer {auth.token}"}
    if isinstance(auth, BasicAuth):
        return httpx.BasicAuth(auth.username, auth.password), {}
    if isinstance(auth, DigestAuth):
        return httpx.DigestAuth(auth.username, auth.password), {}
    return auth, {}  # already an httpx.Auth (or a compatible callable)
