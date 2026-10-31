"""Quirk: does the server **preserve the UID** exactly as sent?

Project policy: ``standard = SUCCESS`` - we require preservation. This is
stricter than RFC 6352 section 5.1, which only requires stored address objects
to have a UID that is unique in the collection; it does not forbid rewriting it
to the resource name (Radicale / Synology do that).
"""

from __future__ import annotations

import uuid

from _checks import Observation, check, vcard
from _profiles import FeatureName, Outcome, Standard

from carddav import DAVError


def test_uid_persistence(writable, baseline, cleanup, quirks_report) -> None:
    feature = FeatureName.IDENTITY_UID_PERSISTENCE
    token = uuid.uuid4().hex[:8]
    sent_uid = f"carddav-uid-{token}"
    stem = f"carddav-persist-{token}"
    href = f"{stem}.vcf"
    detail: dict = {"sent_uid": sent_uid}

    with writable.client() as client:
        book = client.get_addressbooks()[0]
        try:
            book.put_card(vcard(sent_uid, "UID Persistence"), href=href, create_only=True)
        except DAVError as exc:
            outcome = Outcome.FAILURE
            error = type(exc).__name__
            detail.update(status=exc.status)
        else:
            cleanup.append(href)
            stored = book.get_card(href).uid
            detail.update(stored_uid=stored)
            outcome = Outcome.SUCCESS if stored == sent_uid else Outcome.SILENT_FAILURE
            error = None

    check(
        quirks_report,
        writable,
        feature,
        Standard.SUCCESS,
        baseline(feature),
        Observation(outcome, error, detail),
        description=(
            "project policy: require UID preservation (stricter than RFC 6352 "
            "section 5.1, which only requires a UID to exist and be unique)"
        ),
    )
