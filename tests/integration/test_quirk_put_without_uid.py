"""Quirk: what happens when a vCard **without a UID** is PUT?

RFC 6352 section 5.1 requires stored address objects to have a UID. Conformant
outcomes are therefore: the PUT is rejected, or it is accepted and a UID is
assigned. Accepting and storing a UID-less card is a SILENT_FAILURE.
"""

from __future__ import annotations

import uuid

from _checks import Observation, check, vcard
from _profiles import FeatureName, Outcome, Standard

from carddav import DAVError


def test_put_without_uid(writable, baseline, cleanup, quirks_report) -> None:
    feature = FeatureName.WRITE_PUT_WITHOUT_UID
    stem = f"carddav-nouid-{uuid.uuid4().hex[:8]}"
    href = f"{stem}.vcf"
    detail: dict = {"rejected": False, "assigned_uid": None, "stored_vcard": None}

    with writable.client() as client:
        book = client.get_addressbooks()[0]
        try:
            book.put_card(vcard(None, "No UID"), href=href)
        except DAVError as exc:
            # Rejection is conformant: no UID-less object was stored.
            outcome = Outcome.SUCCESS
            detail.update(rejected=True, error=type(exc).__name__, status=exc.status)
        else:
            cleanup.append(href)
            card = book.get_card(href)
            detail.update(assigned_uid=card.uid, stored_vcard=card.text)
            outcome = Outcome.SUCCESS if card.uid is not None else Outcome.SILENT_FAILURE

    check(
        quirks_report,
        writable,
        feature,
        Standard.SUCCESS,
        baseline(feature),
        Observation(outcome, detail=detail),
        description="RFC 6352 section 5.1: stored objects MUST have a UID",
    )
