"""Quirk: does the server rewrite the UID to the **resource name** (file stem)?

``standard = ANY``: RFC 6352 does not require this either way. The probe PUTs a
card with a different UID at ``<stem>.vcf`` and reads it back.
"""

from __future__ import annotations

import uuid

from _checks import Observation, check, vcard
from _profiles import FeatureName, Outcome, Standard

from carddav import DAVError


def test_uid_rewritten_to_resource_name(writable, baseline, cleanup, quirks_report) -> None:
    feature = FeatureName.IDENTITY_UID_REWRITTEN_TO_RESOURCE_NAME
    token = uuid.uuid4().hex[:8]
    sent_uid = f"carddav-uid-{token}"
    stem = f"carddav-rewrite-{token}"
    href = f"{stem}.vcf"
    detail: dict = {"sent_uid": sent_uid, "stem": stem}

    with writable.client() as client:
        book = client.get_addressbooks()[0]
        try:
            book.put_card(vcard(sent_uid, "UID Rewrite"), href=href, create_only=True)
        except DAVError as exc:
            outcome = Outcome.FAILURE
            error = type(exc).__name__
            detail.update(status=exc.status)
        else:
            cleanup.append(href)
            stored = book.get_card(href).uid
            detail.update(stored_uid=stored)
            outcome = Outcome.SUCCESS if stored == stem else Outcome.SILENT_FAILURE
            error = None

    check(
        quirks_report,
        writable,
        feature,
        Standard.ANY,
        baseline(feature),
        Observation(outcome, error, detail),
    )
