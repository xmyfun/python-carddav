"""HTTP backend abstraction.

Everything above this module sees only :class:`Backend` / :class:`Response`.
The concrete backends (``_backend_httpx``, ``_backend_requests``) are the **only**
places allowed to import ``httpx`` or ``requests`` - switching the HTTP stack
means adding one module here, not touching business code.

A backend is a plain object with two methods, so tests can pass their own
(see ``tests/test_backend.py``); no inheritance is required.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ._version import __version__

DEFAULT_TIMEOUT = (5.0, 30.0)  # (connect, read) seconds
USER_AGENT = f"carddav/{__version__}"


class Headers(dict[str, str]):
    """Case-insensitive header mapping (keys are stored lower-case)."""

    def __init__(self, items: Mapping[str, str] | Iterable[tuple[str, str]] = ()) -> None:
        pairs = items.items() if isinstance(items, Mapping) else items
        super().__init__((str(k).lower(), str(v)) for k, v in pairs)

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        return super().get(key.lower(), default)

    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.lower())

    def __contains__(self, key: object) -> bool:
        return super().__contains__(str(key).lower())


@dataclass(frozen=True)
class Response:
    """The only response shape the library understands.

    Deliberately smaller than ``requests.Response`` / ``httpx.Response``: just
    the six things ``_dav`` actually reads. ``history`` holds redirect URLs.
    """

    status_code: int
    content: bytes
    text: str
    headers: Headers = field(default_factory=Headers)
    url: str = ""
    history: tuple[str, ...] = ()


class Backend(Protocol):
    """Transport-level HTTP backend."""

    name: str

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        follow_redirects: bool = True,
    ) -> Response: ...

    def close(self) -> None: ...


def make_backend(
    backend: str | Backend = "httpx",
    *,
    auth: object | None = None,
    verify: bool = True,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    http2: bool = False,
) -> Backend:
    """Build a backend by name, or return *backend* unchanged if it is an object.

    ``"httpx"`` (default) and ``"requests"`` (optional extra) are built in;
    anything else is rejected rather than guessed.
    """
    if not isinstance(backend, str):
        return backend

    name = backend.strip().lower()
    if name == "httpx":
        from ._backend_httpx import HttpxBackend

        return HttpxBackend(auth=auth, verify=verify, timeout=timeout, http2=http2)
    if name == "requests":
        try:
            from ._backend_requests import RequestsBackend
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise ImportError(
                "the requests backend needs an optional dependency: "
                "pip install 'carddav[requests]'"
            ) from exc
        return RequestsBackend(auth=auth, verify=verify, timeout=timeout)
    raise ValueError(
        f"unknown backend {backend!r}; expected 'httpx', 'requests', or a Backend object"
    )
