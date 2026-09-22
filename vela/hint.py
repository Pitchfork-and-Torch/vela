"""std.hint ingress: ASCENT-D / Orb fail-closed admit.

Stale age, role mismatch, integrity failure, or absence => None.
None is not a hop oracle. Role + age checks are not a PKI.
Flagship Reach stays defined without hints; bare hint.ascent
arithmetic remains a type error in the checker.
"""
from __future__ import annotations

from dataclasses import dataclass

# Channels named in the language surface (hint.ascent / hint.orb / ...).
HINT_CHANNELS = frozenset({"ascent", "orb", "orbital"})

# Wire roles for ASCENT-D / Orb ingest. Mismatch erases to None.
HINT_ROLES = frozenset({"ascent-d", "orb", "orbital"})

# Honest-but-stale ceiling. Not a hop schedule; erase past this.
DEFAULT_MAX_AGE_S = 2.0


@dataclass(frozen=True)
class PathHint:
    """Admitted path hint after fail-closed ingress."""

    role: str
    channel: str
    age_s: float


def admit_hint(
    *,
    present: bool,
    role: str | None,
    expected_role: str,
    age_s: float | None,
    channel: str = "ascent",
    max_age_s: float = DEFAULT_MAX_AGE_S,
    integrity_ok: bool = True,
) -> PathHint | None:
    """Admit an ASCENT-D / Orb hint or return None (fail-closed).

    Missing, corrupt MAC/integrity, unknown/mismatched role, unknown
    channel, negative/missing age, or age past max_age_s all erase.
    Does not invent a next-hop time from absence.
    """
    if not present:
        return None
    if not integrity_ok:
        return None
    if role is None or expected_role is None:
        return None
    role_n = role.strip().lower()
    expect_n = expected_role.strip().lower()
    if role_n not in HINT_ROLES or expect_n not in HINT_ROLES:
        return None
    if role_n != expect_n:
        return None
    chan = (channel or "").strip().lower()
    if chan not in HINT_CHANNELS:
        return None
    if age_s is None or age_s < 0.0 or age_s > max_age_s:
        return None
    return PathHint(role=role_n, channel=chan, age_s=float(age_s))


def is_none(hint: PathHint | None) -> bool:
    return hint is None
