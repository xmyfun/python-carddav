"""Offline tests for the auth value objects and their backend translation."""

from __future__ import annotations

import httpx
import pytest
import requests

from carddav import BasicAuth, BearerAuth, DAVClient, DigestAuth
from carddav._backend_httpx import HttpxBackend
from carddav._backend_requests import RequestsBackend


def test_basic_auth_is_a_plain_value_object() -> None:
    auth = BasicAuth("alice", "s3cret")
    assert (auth.username, auth.password) == ("alice", "s3cret")


def test_bearer_rejects_an_empty_token() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        BearerAuth("")


def test_username_password_become_basic_auth() -> None:
    assert DAVClient._make_auth(None, "alice", "s3cret") == BasicAuth("alice", "s3cret")


def test_explicit_auth_wins_over_credentials() -> None:
    bearer = BearerAuth("tok-123")
    assert DAVClient._make_auth(bearer, "alice", "s3cret") is bearer


def test_no_credentials_means_no_auth() -> None:
    assert DAVClient._make_auth(None, None, None) is None


def test_httpx_backend_sends_bearer_as_a_header() -> None:
    backend = HttpxBackend(auth=BearerAuth("tok-123"))
    try:
        assert backend._client.headers["Authorization"] == "Bearer tok-123"
    finally:
        backend.close()


def test_httpx_backend_maps_basic_and_digest() -> None:
    basic = HttpxBackend(auth=BasicAuth("u", "p"))
    try:
        assert isinstance(basic._client.auth, httpx.BasicAuth)
    finally:
        basic.close()

    digest = HttpxBackend(auth=DigestAuth("u", "p"))
    try:
        assert isinstance(digest._client.auth, httpx.DigestAuth)
    finally:
        digest.close()


def test_requests_backend_maps_basic_and_digest() -> None:
    basic = RequestsBackend(auth=BasicAuth("u", "p"))
    try:
        assert isinstance(basic._session.auth, requests.auth.HTTPBasicAuth)
    finally:
        basic.close()

    digest = RequestsBackend(auth=DigestAuth("u", "p"))
    try:
        assert isinstance(digest._session.auth, requests.auth.HTTPDigestAuth)
    finally:
        digest.close()


def test_client_stores_the_chosen_auth_on_its_backend() -> None:
    client = DAVClient("http://example.org/remote.php/dav/", auth=BearerAuth("tok-123"))
    try:
        assert client.transport.backend._client.headers["Authorization"] == "Bearer tok-123"
    finally:
        client.close()


def test_client_can_select_the_requests_backend() -> None:
    client = DAVClient("http://example.org/remote.php/dav/", backend="requests")
    try:
        assert client.transport.backend.name == "requests"
    finally:
        client.close()
