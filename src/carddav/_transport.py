"""HTTP policy layer - retries, timeouts, cross-host warnings.

All library traffic goes through :meth:`Transport.request`; the wire protocol is
delegated to a :class:`~carddav._http.Backend` (httpx by default, requests
optional, or any object with the same two methods - that is also how tests
inject a fake).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from urllib.parse import urlparse

from ._http import DEFAULT_TIMEOUT, Backend, Response, make_backend
from .errors import TransportError

_IDEMPOTENT = {"GET", "HEAD", "OPTIONS", "PROPFIND", "REPORT"}

logger = logging.getLogger("carddav")


class Transport:
    """Applies the library's HTTP policy on top of a pluggable backend."""

    def __init__(
        self,
        backend: Backend | None = None,
        *,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    ):
        self.backend = backend if backend is not None else make_backend(timeout=timeout)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        follow_redirects: bool = True,
    ) -> Response:
        """Send a request; retries only idempotent methods on 5xx/network error.

        Write methods (``PUT``/``POST``/``DELETE``) are never retried
        (``internal/02`` section 6).
        """
        method_u = method.upper()
        attempts = 2 if method_u in _IDEMPOTENT else 1
        last_exc: Exception | None = None

        for attempt in range(attempts):
            try:
                resp = self.backend.request(
                    method_u,
                    url,
                    headers=headers,
                    content=content,
                    follow_redirects=follow_redirects,
                )
            except TransportError as exc:
                last_exc = exc
                if method_u not in _IDEMPOTENT or attempt + 1 == attempts:
                    raise
                time.sleep(0.5 * (attempt + 1))
                continue

            self._warn_cross_host(url, resp)
            if method_u in _IDEMPOTENT and resp.status_code >= 500 and attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
                continue
            return resp

        # Unreachable for non-idempotent (attempts == 1) and idempotent paths
        # above always return or raise; kept for type-checkers.
        raise TransportError(f"{method_u} {url} failed") from last_exc

    def close(self) -> None:
        self.backend.close()

    @staticmethod
    def _warn_cross_host(url: str, resp: Response) -> None:
        """Warn if a redirect moved the request to a different host."""
        if not resp.history:
            return
        orig_host = urlparse(url).netloc
        for hop in resp.history:
            hop_host = urlparse(hop).netloc
            if hop_host and hop_host != orig_host:
                logger.warning(
                    "cross-host redirect %s -> %s (Authorization header may have been forwarded)",
                    orig_host,
                    hop,
                )
                return
