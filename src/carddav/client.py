"""The DAVClient - session lifecycle and explicit discovery.

Construction only sets up the connection (and resolves a bare host via RFC 6764
``.well-known/carddav``). It does **not** talk to the server beyond that.

Discovery is triggered explicitly by :meth:`get_principal` /
:meth:`get_addressbooks`, which walk the RFC 6352 chain
(well-known -> ``current-user-principal`` -> ``addressbook-home-set`` -> address
books). The entry URL may be a bare host, a principal URL, an
addressbook-home-set URL, or a specific addressbook URL - discovery starts from
whatever was given (see ``internal/02`` section 12).
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from . import _dav, _xml
from ._http import DEFAULT_TIMEOUT, Backend, make_backend
from ._transport import Transport
from .addressbook import AddressBook
from .auth import AuthLike, BasicAuth
from .errors import DAVError, DiscoveryError
from .principal import Principal


def _abs(base: str, ref: str) -> str:
    return urljoin(base.rstrip("/") + "/", ref)


def _looks_like_dav_path(url: str) -> bool:
    """True for a URL that plausibly points at a DAV collection, not a web page.

    Colon/``.web``/``.html``-style targets are rejected so a redirect to a UI
    page (Synology's ``.web``) never becomes the discovery base. A last segment
    without a dot (``/remote.php/dav``) is accepted.
    """
    path = urlparse(url).path
    if path.endswith("/"):
        return True
    last = path.rsplit("/", 1)[-1]
    return bool(last) and "." not in last


def get_davclient(
    url: str,
    username: str | None = None,
    password: str | None = None,
    auth: AuthLike | object | None = None,
    *,
    backend: str | Backend = "httpx",
    verify: bool = True,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    http2: bool = False,
) -> DAVClient:
    """Create a :class:`DAVClient`. Construction only sets up the connection.

    ``backend``: ``"httpx"`` (default), ``"requests"`` (needs the extra), or any
    object implementing the ``Backend`` protocol - the latter is how tests and
    future HTTP stacks plug in without patching this library.
    """
    return DAVClient(
        url,
        username=username,
        password=password,
        auth=auth,
        backend=backend,
        verify=verify,
        timeout=timeout,
        http2=http2,
    )


class DAVClient:
    """Talks to one CardDAV server over one pluggable HTTP backend."""

    def __init__(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
        auth: AuthLike | object | None = None,
        *,
        backend: str | Backend = "httpx",
        verify: bool = True,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        http2: bool = False,
    ) -> None:
        self.transport = Transport(
            make_backend(
                backend,
                auth=self._make_auth(auth, username, password),
                verify=verify,
                timeout=timeout,
                http2=http2,
            )
        )
        # Bare host (no path) is resolved via RFC 6764 `.well-known/carddav`;
        # any URL with a path is used as-is. No PROPFIND happens here - discovery
        # is explicit (get_principal / get_addressbooks).
        self.url = self._resolve_base(url)

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> DAVClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_principal(self) -> Principal:
        """Discover the authenticated principal from the entry URL (RFC 6352).

        The entry URL may be a bare host, a principal URL, an
        addressbook-home-set URL, or a specific addressbook URL. Discovery starts
        from whatever was given and walks down the chain
        (``current-user-principal`` -> ``addressbook-home-set`` -> address books).
        """
        # Light probe first: is the entry URL itself an addressbook? Radicale
        # answers principal queries on a collection with 401, so ask resourcetype
        # before anything that touches the principal.
        try:
            root = _dav.propfind(self.transport, self.url, _xml.propfind_resourcetype(), depth="0")
            responses = _xml.iter_responses(root)
        except DAVError:
            # The entry URL is unusable for a resourcetype probe (e.g. Radicale
            # 401 on a collection) - fall back to treating it as the discovery
            # root.
            return Principal(self, self.url)

        if not responses:
            raise DiscoveryError("PROPFIND returned an empty multistatus", href=self.url)
        resp = responses[0]
        if _xml.response_has(resp, _xml.CARDDAV_NS, "addressbook"):
            return Principal(self, self.url, direct_addressbook=self.url)

        # Not a direct addressbook: discover principal / home-set.
        try:
            root2 = _dav.propfind(self.transport, self.url, _xml.propfind_discovery(), depth="0")
            resp2 = _xml.iter_responses(root2)[0]
        except DAVError:
            # Radicale etc. may 401 on principal queries for a collection; the
            # entry URL is then the discovery root itself.
            return Principal(self, self.url)

        principal_href = _xml.find_child_href(resp2, _xml.DAV_NS, "current-user-principal")
        if principal_href:
            return Principal(self, _abs(self.url, principal_href))

        home_set = _xml.find_child_href(resp2, _xml.CARDDAV_NS, "addressbook-home-set")
        if home_set:
            return Principal(self, _abs(self.url, home_set))

        # A collection but with no principal/home-set advertised (e.g. a home-set
        # container, or a server that omits the principal). Treat the entry URL
        # itself as the discovery root - NOT as a single addressbook.
        if _xml.response_has(resp2, _xml.DAV_NS, "collection"):
            return Principal(self, self.url)

        raise DiscoveryError(
            "could not determine a principal or addressbook from the response",
            href=self.url,
        )

    def get_addressbooks(self) -> list[AddressBook]:
        """Discover and return all address books (convenience for get_principal)."""
        return self.get_principal().get_addressbooks()

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _make_auth(
        auth: AuthLike | object | None, username: str | None, password: str | None
    ) -> AuthLike | object | None:
        if auth is not None:
            return auth
        if username is not None:
            return BasicAuth(username, password or "")
        return None

    def _resolve_base(self, url: str) -> str:
        parsed = urlparse(url)
        # Bare host (no path) -> try .well-known/carddav first (RFC 6764).
        if parsed.path not in ("", "/"):
            # Any URL with a path (principal, home-set or addressbook collection)
            # is used as-is - the trailing slash is significant for some servers
            # (Radicale).
            return url
        base = url.rstrip("/")
        current = base + "/.well-known/carddav"
        # Follow the redirect chain manually: the RFC 6764 target is the DAV
        # context path, usually a **collection** URL (trailing slash). Servers
        # may redirect again to a non-DAV web page - Synology sends
        # `/carddav/` -> `.web` ("Radicale works!") - so stop at the first
        # DAV-looking hop instead of chasing the whole chain.
        for _ in range(5):
            try:
                resp = self.transport.request("GET", current, follow_redirects=False)
            except Exception:  # noqa: BLE001 - fall back to the URL as given
                return base
            location = resp.headers.get("Location")
            if resp.status_code not in (301, 302, 303, 307, 308) or not location:
                break
            current = urljoin(current, location)
            if _looks_like_dav_path(current):
                # Keep a trailing slash: Synology answers 405 on `/carddav`
                # but speaks DAV on `/carddav/`.
                return current
        return base
