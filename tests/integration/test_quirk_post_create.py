"""Quirk: can a card be created with ``POST`` to the collection?

``standard = ANY``: RFC 6352 defines ``PUT`` (not ``POST``) for creating cards,
so there is no normative outcome. The probe still runs on every server and the
observation is recorded.
"""

from __future__ import annotations

import uuid

from _checks import Observation, check, vcard
from _profiles import FeatureName, Outcome, Standard

from carddav import DAVError


def test_post_create(writable, baseline, cleanup, quirks_report) -> None:
    feature = FeatureName.WRITE_POST_CREATE
    uid = f"carddav-post-{uuid.uuid4().hex[:8]}"
    href = None
    error = None
    detail: dict = {}

    with writable.client() as client:
        book = client.get_addressbooks()[0]
        try:
            href = book.post_card(vcard(uid, "Post Create"))
        except DAVError as exc:
            outcome = Outcome.FAILURE
            error = type(exc).__name__
            detail = {"status": exc.status}
        else:
            cleanup.append(href)
            try:
                stored = book.get_card(href)
            except DAVError:
                outcome = Outcome.SILENT_FAILURE
                detail = {"href": href, "retrievable": False}
            else:
                outcome = Outcome.SUCCESS if stored.uid == uid else Outcome.SILENT_FAILURE
                detail = {"href": href, "retrievable": True, "stored_uid": stored.uid}

    check(
        quirks_report,
        writable,
        feature,
        Standard.ANY,
        baseline(feature),
        Observation(outcome, error, detail),
    )
