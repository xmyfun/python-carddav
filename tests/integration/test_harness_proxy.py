"""Harness regression: local clients bypass any HTTP proxy (``trust_env=False``).

This is a property of the local fixtures, not of a CardDAV server, so it only
runs for ``server.kind == "local"``.
"""

from __future__ import annotations

import uuid

import pytest
from _checks import vcard


def test_local_server_bypasses_proxy(server, cleanup) -> None:
    if server.kind != "local":
        pytest.skip("local-only harness regression")
    with server.client() as client:
        book = client.get_addressbooks()[0]
        uid = f"carddav-noproxy-{uuid.uuid4().hex[:8]}"
        book.put_card(vcard(uid, "No Proxy"), create_only=True)
        cleanup.append(f"{uid}.vcf")
        assert book.get_card(f"{uid}.vcf").uid == uid
