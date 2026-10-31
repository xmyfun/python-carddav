"""Shared fixtures for the integration suite.

Every test runs against the **server catalog** in ``_catalog.py``: local test
servers (Radicale/Xandikos, launched and destroyed by these fixtures) plus the
remote real servers configured in ``servers.ini``. A single ``server`` fixture is
parametrized over that catalog; ``pytest_generate_tests`` attaches the per-server
marks (``local`` / ``remote``), because ``@pytest.fixture(params=...)`` cannot
carry ``pytest.param(marks=...)``.

Those marks are **selection labels only** - they never decide whether a test
runs. Nothing filters ``remote`` out by default: a remote server is added to the
catalog only when ``servers.ini`` configures it, and ``server`` skips it when
credentials are incomplete or the host is unreachable.

Safety rules:

* local test servers are launched by the test run and destroyed afterwards -
  writes are always allowed;
* remote real servers may hold real data - write tests require ``--allow-write``
  and every write test cleans up after itself (prefix-scoped, in fixture teardown).
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from _catalog import CATALOG
from _helpers import load_creds
from _profiles import Feature, FeatureName, ServerProfile

from carddav import BearerAuth, DAVClient, DAVError, TransportError, get_davclient

_USER, _PASS = "testuser", "testpass"
_MKCOL_BODY = (
    '<?xml version="1.0"?>'
    '<a:mkcol xmlns:a="DAV:" xmlns:b="urn:ietf:params:xml:ns:carddav">'
    "<a:set><a:prop>"
    "<a:resourcetype><a:collection/><b:addressbook/></a:resourcetype>"
    "<a:displayname>contacts</a:displayname>"
    "</a:prop></a:set></a:mkcol>"
)


@dataclass
class ServerHandle:
    """A server under test: its identity, kind, baseline profile and client factory."""

    id: str
    kind: str  # "local" | "remote"
    profile: ServerProfile | None
    factory: Callable[[], DAVClient]

    @contextlib.contextmanager
    def client(self):
        with self.factory() as client:
            yield client


@dataclass
class _LocalServer:
    id: str
    url: str
    username: str
    password: str
    proc: subprocess.Popen

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize ``server`` over the catalog, with per-server marks."""
    if "server" in metafunc.fixturenames:
        metafunc.parametrize(
            "server",
            [pytest.param(spec, id=spec.id, marks=spec.marks) for spec in CATALOG],
            indirect=True,
        )


@pytest.fixture
def allow_write(pytestconfig: pytest.Config) -> bool:
    return bool(pytestconfig.getoption("--allow-write"))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, trust_env=False, timeout=1.0)
            if r.status_code < 500:
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"server at {url} did not become ready")


def _mkcol_addressbook(url: str) -> int:
    r = httpx.request(
        "MKCOL",
        url,
        content=_MKCOL_BODY,
        auth=(_USER, _PASS),
        headers={"Content-Type": "application/xml; charset=utf-8"},
        trust_env=False,
        timeout=10.0,
    )
    return r.status_code


def _package_present(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _spin_up_radicale() -> _LocalServer:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    d = Path(tempfile.mkdtemp(prefix="carddav-test-rad-"))
    data = d / "data"
    data.mkdir()
    (d / "users").write_text(f"{_USER}:{_PASS}\n")
    cfg = d / "radicale.conf"
    cfg.write_text(
        "[server]\n"
        f"hosts = 127.0.0.1:{port}\n"
        "[auth]\n"
        "type = htpasswd\n"
        f"htpasswd_filename = {d / 'users'}\n"
        "htpasswd_encryption = plain\n"
        "[storage]\n"
        f"filesystem_folder = {data}\n"
        "[rights]\n"
        "type = authenticated\n"
    )
    log = d / "server.log"
    env = {**os.environ, "PYTHONPATH": ""}  # see internal/06 §3.1
    proc = subprocess.Popen(
        [sys.executable, "-m", "radicale", "-C", str(cfg)],
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        env=env,
    )
    try:
        _wait_for(base + "/")
        book_url = base + f"/{_USER}/contacts/"
        code = _mkcol_addressbook(book_url)
        assert code in (201, 207), f"MKCOL failed with {code}"
    except Exception:
        proc.terminate()
        raise
    return _LocalServer(id="radicale", url=book_url, username=_USER, password=_PASS, proc=proc)


def _spin_up_xandikos() -> _LocalServer:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    d = Path(tempfile.mkdtemp(prefix="carddav-test-xan-"))
    log = d / "server.log"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "xandikos",
            "serve",
            "--defaults",
            "--autocreate",
            "-d",
            str(d),
            "-l",
            "127.0.0.1",
            "-p",
            str(port),
        ],
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
    )
    try:
        book_url = base + "/user/contacts/addressbook/"
        _wait_for(book_url)
    except Exception:
        proc.terminate()
        raise
    return _LocalServer(id="xandikos", url=book_url, username="user", password="", proc=proc)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def local_servers() -> Callable[[str], _LocalServer]:
    """Start each local test server at most once per session; stop them at the end.

    The servers are disposable sandboxes owned by the test run, so sharing one
    process across every test item is safe (each test writes only under its own
    unique prefix and cleans up). Starting them per test item instead would pay
    a process launch, a port bind and a readiness poll for every single test.
    """
    started: dict[str, _LocalServer] = {}

    def get(server_id: str) -> _LocalServer:
        server = started.get(server_id)
        if server is None:
            server = _spin_up_xandikos() if server_id == "xandikos" else _spin_up_radicale()
            started[server_id] = server
        return server

    yield get
    for server in started.values():
        server.stop()


def _probe_remote(server_id: str) -> str | None:
    """Return a skip reason if ``server_id`` is unusable, else ``None``."""
    creds = load_creds(server_id)
    if creds is None:
        return f"[{server_id}] not configured in tests/integration/servers.ini"
    url, username, password, auth_type, verify = creds
    auth = BearerAuth(password) if auth_type == "bearer" else None
    probe = get_davclient(
        url,
        username=None if auth else username,
        password=None if auth else password,
        auth=auth,
        verify=verify,
    )
    try:
        books = probe.get_addressbooks()
    except TransportError as exc:
        return f"[{server_id}] unreachable or not a CardDAV server: {exc}"
    except DAVError:
        return f"[{server_id}] rejected discovery (server unavailable)"
    finally:
        probe.close()
    if not books:
        return f"[{server_id}] no addressbooks discovered"
    return None


@pytest.fixture(scope="session")
def remote_status() -> Callable[[str], str | None]:
    """Probe each remote server once per session (a slow host can cost seconds)."""
    cache: dict[str, str | None] = {}

    def status(server_id: str) -> str | None:
        if server_id not in cache:
            cache[server_id] = _probe_remote(server_id)
        return cache[server_id]

    return status


@pytest.fixture
def server(
    request: pytest.FixtureRequest,
    local_servers: Callable[[str], _LocalServer],
    remote_status: Callable[[str], str | None],
):
    """Yield a ``ServerHandle`` for one catalog entry (local or remote)."""
    spec = request.param
    if spec.kind == "local":
        if not _package_present(spec.id):
            pytest.skip(f"{spec.id} not installed (add it via the dev dependency group)")
        local = local_servers(spec.id)
        yield ServerHandle(
            id=spec.id,
            kind="local",
            profile=spec.profile,
            factory=lambda: get_davclient(
                local.url,
                username=local.username,
                password=local.password,
                trust_env=False,
            ),
        )
        return

    reason = remote_status(spec.id)
    if reason is not None:
        pytest.skip(reason)
    creds = load_creds(spec.id)
    if creds is None:  # defensive: remote_status() already checked this
        pytest.skip(f"[{spec.id}] not configured in tests/integration/servers.ini")
    url, username, password, auth_type, verify = creds
    auth = BearerAuth(password) if auth_type == "bearer" else None

    def factory() -> DAVClient:
        return get_davclient(
            url,
            username=None if auth else username,
            password=None if auth else password,
            auth=auth,
            verify=verify,
        )

    yield ServerHandle(id=spec.id, kind="remote", profile=spec.profile, factory=factory)


@pytest.fixture
def writable(server: ServerHandle, allow_write: bool) -> ServerHandle:
    """A server that may be written to: local always, remote only with --allow-write."""
    if server.kind == "remote" and not allow_write:
        pytest.skip(f"[{server.id}] --allow-write not set; skipping write tests")
    return server


@pytest.fixture
def baseline(server: ServerHandle) -> Callable[[FeatureName], Feature | None]:
    """Look up the recorded baseline for a feature; None means "not measured"."""

    def get(feature: FeatureName) -> Feature | None:
        if server.profile is None:
            return None
        return server.profile.features.get(feature.value)

    return get


@pytest.fixture
def cleanup(server: ServerHandle):
    """Track hrefs created by a write test and delete them in teardown."""
    created: list[str] = []
    yield created
    if not created:
        return
    try:
        with server.client() as client:
            book = client.get_addressbooks()[0]
            for href in created:
                try:
                    book.delete_card(href)
                except DAVError:
                    pass
    except Exception:  # best effort: never mask the test result
        pass


@pytest.fixture(scope="session")
def quirks_report():
    """Collect quirk-check records and write them to out/quirks-report.json."""
    records: list[dict] = []
    yield records
    if not records:
        return
    out = Path("out")
    if not out.exists():
        out.mkdir(parents=True, exist_ok=True)
    (out / "quirks-report.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
