"""Read explicit capture identities without treating missing values as wildcards."""

from collections.abc import Mapping

from config import refactor_modes
from utils.capture.shadow import compare


def capture_keys(row: Mapping) -> frozenset[tuple[str, str, str, str | None, str | None]]:
    """S1 live runs and sync receipts encode the same stream in different envelopes."""
    envelope = row.get('capture_evidence') or {}
    if not isinstance(envelope, Mapping):
        return frozenset()
    # Detailed stream positions outrank an envelope's optional coarse metadata.
    # Otherwise a default channel/epoch at the top could hide a nested mismatch.
    values = [*(envelope.get('runs') or []), *(envelope.get('receipts') or [])] or [envelope]
    keys = set()
    for item in values:
        if not isinstance(item, Mapping) or not item.get('capture_root'):
            continue
        # Metadata may encode the integer S1 epoch as a string.
        keys.add(
            (
                str(item['capture_root']),
                str(item.get('channel') or 'default'),
                str(item.get('clock_epoch', 'default')),
                row.get('client_device_id') or envelope.get('client_device_id'),
                recording_session(row),
            )
        )
    return frozenset(keys)


def recording_session(row: Mapping) -> str | None:
    external = row.get('external_data') or {}
    evidence = row.get('capture_evidence') or {}
    return (
        row.get('recording_session_id') or evidence.get('recording_session_id') or external.get('recording_session_id')
    )


def compatible_keys(left: Mapping, right: Mapping) -> bool:
    """An explicit key on either side requires equality, never temporal inference."""
    a, b = capture_keys(left), capture_keys(right)
    if (a or b) and (not a or not b or not a.intersection(b)):
        return False
    a_session, b_session = recording_session(left), recording_session(right)
    return not (a_session and b_session and a_session != b_session)


def same_explicit_key(left: Mapping, right: Mapping) -> bool:
    return bool(capture_keys(left) and capture_keys(right) and compatible_keys(left, right))


def assignment_keys_compatible(left: Mapping, right: Mapping, uid: str | None) -> bool:
    """Keep legacy partition decisions in shadow while reporting key conflicts."""
    if not refactor_modes.shadow_or_serve('CAPTURE_COVERAGE_MODE'):
        return True
    compatible = compatible_keys(left, right)
    if not compatible:
        compare('capture_key', 'disagree')
    return compatible if refactor_modes.serving_for('CAPTURE_COVERAGE_MODE', uid) else True


def persist_identity(uid: str, result: dict, incoming: Mapping, canonical: Mapping | None) -> None:
    """Keep a served stream's session identity after legacy receipt compaction."""
    if not refactor_modes.serving_for('CAPTURE_COVERAGE_MODE', uid):
        return
    session = recording_session(canonical or {}) or recording_session(incoming)
    if session:
        external = dict(result.get('external_data') or {})
        external.setdefault('recording_session_id', session)
        result['external_data'] = external
