"""Comparison and reporting helpers for the quirk checks.

``standard / baseline / observed -> verdict``:

* ``standard`` - the feature's normative expectation (from the test);
* ``baseline`` - the recorded behaviour for this server (from the profile), or
  ``None`` when this server/feature was never measured;
* ``observed`` - what the probe saw this run.

A baseline overrides the standard for that server (we accept the recorded
deviation); if there is no baseline, the standard is the expectation. When both
are absent (``Standard.ANY`` and no baseline) there is nothing to compare, so the
check is recorded and skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pytest
from _profiles import Feature, FeatureName, Outcome, Standard


class Verdict(str, Enum):
    MATCH = "match"
    REGRESSION = "regression"
    IMPROVEMENT = "improvement"
    CHANGE = "change"


@dataclass(frozen=True)
class Observation:
    """What one probe saw. ``detail`` carries feature-specific diagnostics."""

    outcome: Outcome
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def vcard(uid: str | None, fn: str) -> bytes:
    """Build a minimal vCard 3.0; ``uid=None`` omits the UID property."""
    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    if uid is not None:
        lines.append(f"UID:{uid}")
    lines.extend([f"FN:{fn}", "N:Test;CardDAV;;;", "END:VCARD"])
    return ("\r\n".join(lines) + "\r\n").encode()


def href_of(book: Any, uid: str) -> str:
    """Find the href of the card whose UID is ``uid`` (raises if absent)."""
    for card in book.get_all_cards():
        if card.uid == uid:
            return card.href
    raise AssertionError(f"card {uid} not found after create")


def _standard_outcome(standard: Standard) -> Outcome | None:
    if standard is Standard.SUCCESS:
        return Outcome.SUCCESS
    if standard is Standard.FAILURE:
        return Outcome.FAILURE
    return None


def compare(
    standard: Standard,
    baseline: Feature | None,
    observed: Observation,
) -> Verdict | None:
    """Compare the observed outcome with the server's baseline (or the standard)."""
    if observed.outcome is Outcome.UNKNOWN:
        return None

    std = _standard_outcome(standard)
    expected = baseline.outcome if baseline is not None and baseline.outcome is not None else std
    if expected is None:
        return None  # Standard.ANY and no baseline: nothing to compare

    if observed.outcome == expected:
        if baseline is not None and baseline.error is not None and observed.error != baseline.error:
            return Verdict.CHANGE
        return Verdict.MATCH

    if std is None:
        return Verdict.CHANGE
    if observed.outcome == std:
        return Verdict.IMPROVEMENT
    if expected == std:
        return Verdict.REGRESSION
    return Verdict.CHANGE


def record(
    report: list[dict[str, Any]],
    server: Any,
    feature: FeatureName,
    standard: Standard,
    baseline: Feature | None,
    observed: Observation,
    verdict: Verdict | None,
) -> None:
    """Append one quirk-check row to *report*.

    The report **schema lives here only**: every row - whether its verdict comes
    from :func:`compare` or from a test that applies a stricter predicate of its
    own - must go through this function, so a schema change has exactly one place
    to land.
    """
    report.append(
        {
            "server": server.id,
            "server_kind": server.kind,
            "feature": feature.value,
            "standard": standard.value,
            "baseline": baseline.outcome.value if baseline and baseline.outcome else None,
            "baseline_error": baseline.error if baseline else None,
            "observed": observed.outcome.value,
            "observed_error": observed.error,
            "verdict": verdict.value if verdict is not None else None,
            "detail": observed.detail,
        }
    )


def check(
    report: list[dict[str, Any]],
    server: Any,
    feature: FeatureName,
    standard: Standard,
    baseline: Feature | None,
    observed: Observation,
    *,
    description: str = "",
) -> None:
    """Record the check, then pass / fail / skip according to the verdict.

    ``description`` is appended to the failure message only - it explains *why*
    this feature has the expectation it does (an RFC clause, or a project policy
    that is stricter than the RFC). It never affects the verdict.
    """
    verdict = compare(standard, baseline, observed)
    record(report, server, feature, standard, baseline, observed, verdict)

    if verdict is None:
        pytest.skip(
            f"[{server.id}] {feature.value}: no comparable baseline/standard; "
            f"observed={observed.outcome.value} recorded"
        )
    if verdict is Verdict.MATCH:
        return

    baseline_text = baseline.outcome.value if baseline and baseline.outcome else "none"
    pytest.fail(
        f"[{server.id}] {feature.value}: {verdict.value}; "
        f"standard={standard.value}, baseline={baseline_text}, "
        f"observed={observed.outcome.value}" + (f"; {description}" if description else ""),
        pytrace=False,
    )
