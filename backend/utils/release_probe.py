"""Single source of truth for the synthetic release-probe identity.

RELEASE_PROBE_UID names the fixed non-human uid minted by
``scripts/firebase_release_probe_token.py`` for CI release probes. Real
signups always receive server-generated Firebase uids, so a token bearing
this uid can only be minted from the Firebase service-account signer used
by the deploy identity (project-validated, five-minute TTL).

Gate convention: every desktop post-processing gate in
``utils/conversations/process_conversation.py`` must consult
:func:`is_release_probe_uid` so the release probe exercises the full
terminal desktop path. A new desktop gate that forgets the predicate makes
the dev pusher release probe fail loudly in CI — that is intended, and it
forces the gate author to consciously exempt or justify the gate.
"""

from __future__ import annotations

RELEASE_PROBE_UID = 'omi-release-probe'


def is_release_probe_uid(uid: object) -> bool:
    """Exact-match check for the synthetic release-probe identity.

    Deliberately strict equality: no prefix, suffix, or case-insensitive
    matching, so a lookalike uid can never inherit the exemption.
    """
    return isinstance(uid, str) and uid == RELEASE_PROBE_UID
