"""Quirk: how does the server react to an **invalid sync-token**?

``standard = FAILURE``: RFC 6578 section 3.2 makes ``DAV:valid-sync-token`` a
precondition (the token MUST be valid). RFC 4918 section 16 requires the
precondition element to be returned with "an appropriate response status": 403
is the most common, but 412 is also an appropriate status. The probe sends the
REPORT directly so it can inspect the **full** body (the library's exception
snippet is truncated and cannot reliably confirm the precondition element).
"""

from __future__ import annotations

import pytest
from _checks import Observation, Verdict, check, record
from _profiles import FeatureName, Outcome, Standard

from carddav._dav import XML_CT
from carddav._xml import report_sync_collection

_BAD_TOKEN = "urn:uuid:00000000-0000-0000-0000-000000000000"


def _observe(book) -> Observation:
    body = report_sync_collection(_BAD_TOKEN)
    resp = book.client.transport.request(
        "REPORT",
        book.url,
        headers={"Depth": "1", "Content-Type": XML_CT},
        content=body.encode(),
    )
    status = resp.status_code
    text = resp.text
    has_token = "valid-sync-token" in text.lower()
    detail = {"status": status, "has_valid_sync_token": has_token, "body": text[:300]}

    if status == 403 and has_token:
        return Observation(Outcome.FAILURE, "SyncTokenInvalid", detail)
    if status == 412 and has_token:
        return Observation(Outcome.FAILURE, "PreconditionFailed", detail)
    if status >= 400:
        return Observation(Outcome.FAILURE, f"HTTP{status}", detail)
    return Observation(Outcome.SUCCESS, None, detail)


def test_sync_invalid_token(server, baseline, quirks_report) -> None:
    feature = FeatureName.SYNC_INVALID_TOKEN
    with server.client() as client:
        book = client.get_addressbooks()[0]
        observed = _observe(book)

    base = baseline(feature)
    if base is not None:
        check(
            quirks_report,
            server,
            feature,
            Standard.FAILURE,
            base,
            observed,
            description="RFC 6578 section 3.2: invalid sync-token must be rejected",
        )
        return

    # Without a baseline we hold the server to the RFC ourselves rather than via
    # check(): Standard.FAILURE alone would accept *any* 4xx, but RFC 6578
    # section 3.2 also requires the DAV:valid-sync-token precondition element in
    # the body and an "appropriate" status (403 or 412 per RFC 4918 section 16).
    conformant = (
        observed.outcome is Outcome.FAILURE
        and observed.detail.get("has_valid_sync_token") is True
        and observed.error in {"SyncTokenInvalid", "PreconditionFailed"}
    )
    verdict = Verdict.MATCH if conformant else Verdict.REGRESSION
    record(quirks_report, server, feature, Standard.FAILURE, None, observed, verdict)
    if not conformant:
        pytest.fail(
            f"[{server.id}] {feature.value}: invalid sync-token was not rejected "
            f"per RFC 6578 section 3.2 (status={observed.detail.get('status')}, "
            f"has_valid_sync_token={observed.detail.get('has_valid_sync_token')})",
            pytrace=False,
        )
