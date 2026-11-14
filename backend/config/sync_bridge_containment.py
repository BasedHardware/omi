"""Contained-donor bridge merge: default off, with a shadow dry-run and an explicit on.

A sync donor summarized before its live target closed is refused forever by the
``already_processed`` fence. When both the donor's and the target's recorded
segment span exist and the donor's is fully inside the target's, the merge cannot
drop speech the target missed, so the bridge may absorb it. Every other fence
(custody, privacy, partial overlap, open target) still applies.

The switch is a three-value mode, and it is **off** by default:

- ``off``: the pre-change refusal, byte for byte. A processed donor is refused by
  the blanket ``already_processed`` fence; no span is compared and no assignment
  is attempted.
- ``shadow``: run the containment predicate and the span comparison, emit a
  bounded counter and one log line, and return the same refusal. It never
  assigns, tombstones, retracts notes or memories, and never emits an identifier
  or content.
- ``on``: the merge, exactly as reviewed.

Only the documented lowercase words select a mode. An absent, blank, unknown,
misspelled or numeric value resolves ``off`` in every capture-coverage mode, so a
typo disables the merge and never enables it.
"""

import os

ENV = 'SYNC_BRIDGE_CONTAINED_DONOR_MERGE_ENABLED'

MODE_OFF = 'off'
MODE_SHADOW = 'shadow'
MODE_ON = 'on'

# Only these exact lowercase words select a mode. A digit, a blank value, a
# different case, or a typo is not a mode word, so it resolves off.
_SHADOW = frozenset({'shadow'})
_ON = frozenset({'on', 'true', 'yes', 'enabled'})

# The merged predicate (L7a) applies tolerance *inward*: it tightens the target
# window and never loosens it, so a positive value refuses more. The common
# duplicate shape is an identical re-upload whose donor span equals the target's;
# any positive tolerance would refuse that shape forever. Zero is therefore the
# deliberate setting: exact containment passes, and a donor that extends even
# slightly past the target is refused. A stricter value can only refuse more.
CONTAINMENT_TOLERANCE_SECONDS = 0.0


def contained_donor_merge_mode() -> str:
    """Resolve the mode; absent, blank, unknown, misspelled or numeric is ``off``.

    Deliberately not routed through the shared ``default_on`` parser: that
    parser keeps unknown values on in ``CAPTURE_COVERAGE_MODE=serve``, which
    would leave an irreversible merge enabled after a typo. Here only the
    documented lowercase words select ``shadow`` or ``on``; everything else,
    including an absent variable, resolves ``off``.
    """
    raw = os.getenv(ENV)
    if raw is None:
        return MODE_OFF
    value = raw.strip()
    if value in _ON:
        return MODE_ON
    if value in _SHADOW:
        return MODE_SHADOW
    return MODE_OFF


def contained_donor_merge_enabled() -> bool:
    """True only in ``on``; ``shadow`` and ``off`` both refuse the merge."""
    return contained_donor_merge_mode() == MODE_ON
