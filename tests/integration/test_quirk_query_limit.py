"""Quirk: is ``CARDDAV:limit`` honoured?

``standard = ANY``: RFC 6352 section 8.6.2 allows a server to ignore the limit
(truncation is reported with a 507). The probe seeds three matching cards and
asks for one, then records how many came back.
"""

from __future__ import annotations

import uuid

from _checks import Observation, check, vcard
from _profiles import FeatureName, Outcome, Standard

from carddav import DAVError

_QUERY_LIMIT = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:getetag/><c:address-data/></d:prop>"
    '<c:filter><c:prop-filter name="FN">'
    "<c:text-match>{needle}</c:text-match>"
    "</c:prop-filter></c:filter>"
    "<c:limit><c:nresults>1</c:nresults></c:limit>"
    "</c:addressbook-query>"
)


def test_query_limit(writable, baseline, cleanup, quirks_report) -> None:
    feature = FeatureName.QUERY_LIMIT
    prefix = f"carddav-limit-{uuid.uuid4().hex[:8]}"
    detail: dict = {}

    with writable.client() as client:
        book = client.get_addressbooks()[0]
        try:
            for i in range(3):
                uid = f"{prefix}-{i}"
                href = f"{uid}.vcf"
                book.put_card(vcard(uid, f"Limit {prefix} {i}"), href=href, create_only=True)
                cleanup.append(href)
            cards = book.search(_QUERY_LIMIT.format(needle=prefix))
        except DAVError as exc:
            outcome = Outcome.FAILURE
            error = type(exc).__name__
            detail = {"status": exc.status}
        else:
            returned = len(cards)
            outcome = Outcome.SUCCESS if returned == 1 else Outcome.SILENT_FAILURE
            error = None
            detail = {"returned": returned}

    check(
        quirks_report,
        writable,
        feature,
        Standard.ANY,
        baseline(feature),
        Observation(outcome, error, detail),
    )
