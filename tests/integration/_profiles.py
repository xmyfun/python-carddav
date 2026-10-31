"""Server behaviour baselines for the integration/quirk tests.

This module holds **data only** - the recorded behaviour of each server, keyed by
feature name. The test logic (probes, predicates, assertions) lives in the
``test_quirk_*`` modules (one feature : one test).

Model
-----
* ``Outcome`` - the observed/recorded result of one check:

  - ``SUCCESS``        the check's predicate holds;
  - ``FAILURE``        the server rejected the operation (raised a ``DAVError``);
  - ``SILENT_FAILURE`` no error was raised, but the intended effect is absent;
  - ``UNKNOWN``        not measured, or the probe could not classify the result.

* ``Standard`` - the feature's normative expectation (declared in the test, not
  stored per server):

  - ``SUCCESS`` / ``FAILURE`` - RFC requires that outcome;
  - ``ANY``                  - no single correct outcome (optional / vendor-private).

* ``Feature`` - the **baseline** recorded for one (server, feature): the outcome
  and, only when it failed with a meaningful subclass, the exception class.

Absent feature == not measured. ``Outcome.UNKNOWN`` is reserved for observations
that could not be classified.

The comparison ``standard / baseline / observed -> verdict`` lives in ``_checks``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    """Result of one check (recorded baseline, or observed this run)."""

    SUCCESS = "success"
    FAILURE = "failure"  # server rejected (raised a DAVError, not TransportError)
    SILENT_FAILURE = "silent_failure"  # no error, but the intended effect is absent
    UNKNOWN = "unknown"  # not measured / could not classify


class Standard(str, Enum):
    """The feature's normative expectation (test-level, not per server)."""

    SUCCESS = "success"
    FAILURE = "failure"
    ANY = "any"  # no single correct outcome; compare against baseline only


class FeatureName(str, Enum):
    """Stable, hierarchical feature keys (value = dotted name)."""

    WRITE_POST_CREATE = "write.post_create"
    WRITE_PUT_WITHOUT_UID = "write.put_without_uid"
    QUERY_LIMIT = "query.limit"
    SYNC_INVALID_TOKEN = "sync.invalid_token"
    IDENTITY_UID_PERSISTENCE = "identity.uid_persistence"
    IDENTITY_UID_REWRITTEN_TO_RESOURCE_NAME = "identity.uid_rewritten_to_resource_name"


@dataclass(frozen=True)
class Feature:
    """Recorded (baseline) behaviour of one server for one feature."""

    outcome: Outcome | None = None  # None == absent (prefer omitting the key)
    error: str | None = None  # for FAILURE: the exception class, if meaningful
    description: str = ""  # human-readable: behaviour + RFC note


@dataclass(frozen=True)
class ServerProfile:
    """Baselines for one server, plus when they were measured."""

    id: str
    version: str
    measured: str  # ISO date of the measurement, e.g. "2026-10-30"
    features: dict[str, Feature]


# Verified against real servers. Sources: docs/quirks.md §2/§4, internal/06.
KNOWN_PROFILES: dict[str, ServerProfile] = {
    "radicale": ServerProfile(
        id="radicale",
        version="3.9.0",
        measured="2026-10-30",
        features={
            FeatureName.WRITE_POST_CREATE.value: Feature(
                Outcome.FAILURE,
                error="DAVError",
                description="POST -> 405; RFC 6352 defines PUT (not POST) for creating cards",
            ),
            FeatureName.WRITE_PUT_WITHOUT_UID.value: Feature(
                Outcome.SUCCESS,
                description=(
                    "PUT without UID is rejected with MissingUIDError (400); conformant - "
                    "RFC 6352 section 5.1 requires stored address objects to have a UID"
                ),
            ),
            FeatureName.QUERY_LIMIT.value: Feature(
                Outcome.SILENT_FAILURE,
                description="CARDDAV:limit is ignored: 3 matching cards returned for nresults=1",
            ),
            FeatureName.SYNC_INVALID_TOKEN.value: Feature(
                Outcome.FAILURE,
                error="SyncTokenInvalid",
                description="403 + DAV:valid-sync-token (RFC 6578 section 3.2 precondition)",
            ),
            FeatureName.IDENTITY_UID_PERSISTENCE.value: Feature(
                Outcome.SUCCESS,
                description=(
                    "UID is preserved as sent. Re-measured 2026-10-31: PUT at "
                    "'<stem>.vcf' with a different UID keeps that UID (the old matrix "
                    "incorrectly assumed Radicale rewrites it)."
                ),
            ),
            FeatureName.IDENTITY_UID_REWRITTEN_TO_RESOURCE_NAME.value: Feature(
                Outcome.SILENT_FAILURE,
                description=(
                    "UID is kept, not rewritten to the file stem "
                    "(re-measured 2026-10-31; the URL is still the resource identity)"
                ),
            ),
        },
    ),
    "xandikos": ServerProfile(
        id="xandikos",
        version="0.4.10",
        measured="2026-10-30",
        features={
            FeatureName.WRITE_POST_CREATE.value: Feature(
                Outcome.SUCCESS,
                description=(
                    "POST -> 200 with a malformed protocol-relative Location "
                    "(//user/...); the library rebuilds a usable href from collection "
                    "+ trailing segment"
                ),
            ),
            FeatureName.WRITE_PUT_WITHOUT_UID.value: Feature(
                Outcome.SILENT_FAILURE,
                description=(
                    "PUT without UID is accepted but stored without a UID; violates "
                    "RFC 6352 section 5.1 (stored objects MUST have a UID)"
                ),
            ),
            FeatureName.QUERY_LIMIT.value: Feature(
                Outcome.SUCCESS,
                description="CARDDAV:limit is honoured: nresults=1 -> 1 result",
            ),
            FeatureName.SYNC_INVALID_TOKEN.value: Feature(
                Outcome.FAILURE,
                error="PreconditionFailed",
                description=(
                    "412 (instead of the conventional 403); RFC 4918 section 16 allows "
                    "'an appropriate response status', 403 being the most common"
                ),
            ),
            FeatureName.IDENTITY_UID_PERSISTENCE.value: Feature(
                Outcome.SUCCESS,
                description="UID is preserved as sent (the write path round-trips uid)",
            ),
            FeatureName.IDENTITY_UID_REWRITTEN_TO_RESOURCE_NAME.value: Feature(
                Outcome.SILENT_FAILURE,
                description="UID is kept, not rewritten to the file stem",
            ),
        },
    ),
    "synology_contacts": ServerProfile(
        id="synology_contacts",
        version="unknown (DSM Contacts)",
        measured="2026-10-29",
        features={
            FeatureName.WRITE_POST_CREATE.value: Feature(
                Outcome.FAILURE,
                error="DAVError",
                description="POST -> 500; not a create path on this build",
            ),
            # write.put_without_uid: not measured.
            FeatureName.QUERY_LIMIT.value: Feature(
                Outcome.SILENT_FAILURE,
                description="CARDDAV:limit is ignored (all matches returned)",
            ),
            FeatureName.SYNC_INVALID_TOKEN.value: Feature(
                Outcome.SUCCESS,
                description=(
                    "invalid sync-token is silently accepted: 207 + a full listing "
                    "(measured 2026-10-31); deviates from RFC 6578 section 3.2"
                ),
            ),
            FeatureName.IDENTITY_UID_PERSISTENCE.value: Feature(
                Outcome.SILENT_FAILURE,
                description=(
                    "UID is rewritten to the resource name (file stem). Project policy: "
                    "we require preservation, which is stricter than RFC 6352 section 5.1."
                ),
            ),
            FeatureName.IDENTITY_UID_REWRITTEN_TO_RESOURCE_NAME.value: Feature(
                Outcome.SUCCESS,
                description="uid == file stem after PUT at '<stem>.vcf'",
            ),
        },
    ),
    "icloud": ServerProfile(
        id="icloud",
        version="unknown",
        measured="2026-10-31",
        features={
            FeatureName.SYNC_INVALID_TOKEN.value: Feature(
                Outcome.FAILURE,
                error="PreconditionFailed",
                description=(
                    "412 with DAV:valid-sync-token (full body verified 2026-10-31); "
                    "conformant under RFC 4918 section 16 (403 is most common but not required)"
                ),
            ),
            # write/query/identity features: not measured.
        },
    ),
}
