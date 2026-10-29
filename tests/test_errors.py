"""Error-mapping tests: HTTP status code → typed exception."""

from __future__ import annotations

import pytest

from carddav import _dav
from carddav.errors import (
    AuthenticationError,
    DiscoveryError,
    InsufficientStorage,
    MissingUIDError,
    NotFound,
    PermissionDenied,
    PreconditionFailed,
    SyncTokenInvalid,
)


class FakeResponse:
    """Minimal stand-in for requests.Response used by error-mapping tests."""

    def __init__(
        self,
        status_code: int,
        *,
        text: str = "",
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.headers = headers or {}


def test_401() -> None:
    with pytest.raises(AuthenticationError):
        _dav.raise_for_status(FakeResponse(401, text="bad creds"), method="GET")


def test_403_sync_token() -> None:
    with pytest.raises(SyncTokenInvalid):
        _dav.raise_for_status(
            FakeResponse(403, text="<error>valid-sync-token</error>"), method="REPORT"
        )


def test_403_plain() -> None:
    with pytest.raises(PermissionDenied):
        _dav.raise_for_status(FakeResponse(403, text="no"), method="GET")


def test_404() -> None:
    with pytest.raises(NotFound):
        _dav.raise_for_status(FakeResponse(404), method="GET")


def test_412() -> None:
    with pytest.raises(PreconditionFailed):
        _dav.raise_for_status(FakeResponse(412), method="PUT")


def test_507() -> None:
    with pytest.raises(InsufficientStorage):
        _dav.raise_for_status(FakeResponse(507), method="PUT")


def test_400_missing_uid() -> None:
    with pytest.raises(MissingUIDError):
        _dav.raise_for_status(
            FakeResponse(400, text="vCards MUST have a UID property"), method="PUT"
        )


def test_200_is_noop() -> None:
    assert _dav.raise_for_status(FakeResponse(207), method="PROPFIND") is None


def test_get_bytes_rejects_html() -> None:
    from carddav._transport import Transport

    class _T(Transport):
        def request(self, *a: object, **k: object) -> FakeResponse:
            return FakeResponse(200, text="<html>", headers={"Content-Type": "text/html"})

    with pytest.raises(DiscoveryError):
        _dav.get_bytes(_T(), "http://example/x.vcf")
