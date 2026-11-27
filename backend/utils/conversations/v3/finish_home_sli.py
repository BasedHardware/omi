"""Content-free, kill-switch-gated observations for deliberate v3 Finishes."""

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from uuid import UUID

from config.app_channel import APP_CHANNEL_HEADER, app_channel
from config.conversations_v3 import conversations_v3_enabled, v3_intake_held_out
from utils.encryption import ENCRYPTION_SECRET

_logger = logging.getLogger(__name__)
HEADER = 'X-Omi-Finish-Cut'


def enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_FINISH_HOME_SLI', '').strip().lower() == 'on'


def _key(kind: str, uid: str, identifier: str) -> str:
    raw = json.dumps([kind, uid, identifier], separators=(',', ':')).encode()
    return hmac.new(ENCRYPTION_SECRET, b'v3-finish-home-sli:' + raw, hashlib.sha256).hexdigest()[:32]


def home_cohort(uid: str) -> bool:
    """The owner reads v3 Home, so a Finish cut belongs in the v3 denominator.

    The same rule, in the same order, as ``get_conversations`` (routers/conversations.py) uses to choose v3
    Home over legacy Home: stage admission, then the per-owner intake holdout. A held-out owner (SCA-2918)
    Finishes on legacy Home, where no v3 card can ever match the cut. Unknown holdout membership admits
    (``v3_intake_held_out`` fails open), exactly as Home serves that owner v3.
    """
    return conversations_v3_enabled(uid) and not v3_intake_held_out(uid)


def measured(uid: str) -> bool:
    """Synchronous gate for server-side observations: the kill switch, then the Home cohort.

    Call it on a worker thread; async callers use ``measured_async``. Every observation that a Finish cut can
    join (route, window) is collected only for owners whose cuts ``from_request`` admits.
    """
    return enabled() and home_cohort(uid)


async def measured_async(uid: str) -> bool:
    """``measured`` for the event loop: the cohort read runs on the db executor, never on the loop."""
    if not enabled():
        return False
    from utils.executors import db_executor, run_blocking

    return bool(await run_blocking(db_executor, home_cohort, uid))


def _emit(stage: str, **fields) -> None:
    _logger.info('event=v3_finish_home_sli %s', json.dumps({'stage': stage, **fields}, separators=(',', ':')))


@dataclass(frozen=True)
class Finish:
    uid: str
    finish: str | None
    cut_at: datetime
    source: str
    basis: str

    def cut(self) -> None:
        _emit('cut', finish=self.finish, cut_at=self.cut_at.isoformat(), source=self.source, basis=self.basis)

    def bind(
        self, recording_id: str, *, prove_legacy_manual_end: bool = False, visible_card: str | None = None
    ) -> None:
        """Bind this cut to the recording the Finish answered with.

        ``visible_card``: the Finish found that recording's window already on Home with its notes
        (``already_visible``). The cut is then ready at the cut instant, and the readback scores it as a
        0 s success on the ``already_visible`` route instead of waiting for an eligibility write that never
        comes (the Finish changes nothing).
        """
        if self.finish is None:
            # Released clients without the header carry no source or device cut
            # clock. Keep the candidate out of the cohort unless a committed
            # server-side manual-end marker later proves its eligibility.
            finish = _key('legacy-finish', self.uid, recording_id)
            recording = _key('recording', self.uid, recording_id)
            _emit(
                'legacy_candidate',
                finish=finish,
                recording=recording,
                cut_at=self.cut_at.isoformat(),
                source='unknown',
                basis='server_cut',
            )
            if prove_legacy_manual_end:
                observe_legacy_manual_end(self.uid, recording_id)
        else:
            finish = self.finish
            _emit('binding', finish=finish, recording=_key('recording', self.uid, recording_id))
        if visible_card is not None:
            _emit('already_visible', finish=finish, card=_key('card', self.uid, visible_card))


def observe_client_cut(uid: str, identifier: str, cut_at: datetime, source: str) -> None:
    """Record a client cut delivered by the authenticated durable outbox."""
    if not enabled():
        return
    identifier = UUID(identifier).hex
    now = datetime.now(timezone.utc)
    cut_at = cut_at.astimezone(timezone.utc)
    if cut_at > now:
        cut_at, basis = now, 'server_cut'
    else:
        basis = 'client_cut'
    Finish(
        uid,
        _key('finish', uid, identifier),
        cut_at,
        source if source in {'app', 'pendant'} else 'unknown',
        basis,
    ).cut()


def observe_legacy_manual_end(uid: str, recording_id: str) -> None:
    """Record positive proof only after the server commits its manual-end marker."""
    if enabled():
        _emit('legacy_manual_end', recording=_key('recording', uid, recording_id))


def from_request(uid: str, request) -> Finish | None:
    if not enabled() or request is None:
        return None
    header = request.headers.get(HEADER, '')
    if header == 'none' or len(header) > 100:
        return None
    if app_channel(request.headers.get(APP_CHANNEL_HEADER)) != 'beta' or not home_cohort(uid):
        return None
    now = datetime.now(timezone.utc)
    if not header:
        return Finish(uid, None, now, 'unknown', 'server_cut')
    try:
        source, identifier, milliseconds = header.split(',')
        identifier = UUID(identifier).hex
        cut_at = datetime.fromtimestamp(int(milliseconds) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    if source not in {'app', 'pendant'}:
        source = 'unknown'
    if not now - timedelta(minutes=10) <= cut_at <= now:
        # Preserve the denominator on skewed clocks and expose the weaker basis.
        cut_at, basis = now, 'server_cut'
    else:
        basis = 'client_cut'
    finish = Finish(uid, _key('finish', uid, identifier), cut_at, source, basis)
    finish.cut()
    return finish


def observe_route(uid: str, recording_id: str, route: str) -> None:
    """Emit a route signal. Callers gate on ``measured``/``measured_async`` (cohort) first."""
    if enabled() and route in {'fast', 'batch', 'held'}:
        _emit('route', recording=_key('recording', uid, recording_id), route=route)


# A held Finish stays held across every reconcile pass until its awaited transcript lands or its wait
# ends. The readback reads route signals as a set, so one signal per hold is enough; later passes on this
# instance stay quiet. Bounded by entry count and by the longest plausible hold.
HELD_SEEN_SECONDS = 30 * 60
HELD_SEEN_MAX = 4096
_held_seen: dict[str, float] = {}
_held_lock = threading.Lock()


def observe_held(uid: str, recording_ids: Iterable[str], *, clock=time.monotonic) -> None:
    """Emit ``held`` once per held Finish recording (per instance), not on every reconcile pass."""
    if not enabled():
        return
    now = clock()
    fresh = []
    with _held_lock:
        for recording_id in recording_ids:
            key = _key('recording', uid, recording_id)
            seen = _held_seen.get(key)
            if seen is not None and now - seen < HELD_SEEN_SECONDS:
                continue
            _held_seen[key] = now
            fresh.append(recording_id)
        if len(_held_seen) > HELD_SEEN_MAX:
            for key, _ in sorted(_held_seen.items(), key=lambda item: item[1])[: len(_held_seen) - HELD_SEEN_MAX]:
                del _held_seen[key]
    for recording_id in fresh:
        observe_route(uid, recording_id, 'held')


def observe_window(uid: str, recording_id: str, card_id: str) -> None:
    if enabled():
        _emit('window', recording=_key('recording', uid, recording_id), card=_key('card', uid, card_id))


def remember_window(
    windows: MutableMapping[str, tuple[str, ...]],
    *,
    enabled: bool,
    ended: bool,
    window: Mapping[str, object],
    row: Mapping[str, object],
    prior: Mapping[str, object] | None = None,
    was_ended: bool = False,
) -> None:
    """Remember the Finish recordings this commit newly binds to the window's card.

    A recording the stored card already held as an ended manual-end window was bound by the commit that
    ended it, so a later reconcile pass that rewrites the same card does not bind (and emit) it again.
    """
    if not enabled or not ended or not window.get('manual_end'):
        return
    sources = window.get('_finish_sli_sources')
    row_id = row.get('id')
    if not isinstance(sources, (tuple, list)) or not isinstance(row_id, str):
        return
    bound: set[object] = set()
    if prior and was_ended and prior.get('id') == row_id and prior.get('manual_end'):
        stored = prior.get('v3_recording_ids')
        if isinstance(stored, (list, tuple)):
            bound = set(stored)
    typed_sources = tuple(source for source in sources if isinstance(source, str) and source not in bound)
    if typed_sources:
        windows[row_id] = typed_sources


def observe_windows(uid: str, rows: Iterable[Mapping[str, object]], windows: Mapping[str, Sequence[str]]) -> None:
    for row in rows:
        card_id = row.get('id')
        if not isinstance(card_id, str):
            continue
        for recording_id in windows.get(card_id, ()):
            observe_window(uid, recording_id, card_id)


def observe_summary(uid: str, card_id: str) -> None:
    if enabled():
        _emit('summary', card=_key('card', uid, card_id))


def observe_eligible(uid: str, card_id: str) -> None:
    """The scored readiness signal: a committed write left this Finish window Home-eligible with a summary."""
    if enabled():
        _emit('eligible', card=_key('card', uid, card_id))


def home_ready(row: Mapping[str, object]) -> bool:
    """A Finish window that shows its summary on Home: settled, visible and with readable notes.

    Shared by the write-path eligibility signal and the Home-fetch validation. Owner-visibility filters
    that need the stored row (relevance discards, settling fragments) are the caller's, as in Home.
    """
    from utils.conversations.summary_delivery import present

    return bool(
        row.get('v3_derived')
        and row.get('manual_end')
        and row.get('tile_state') == 'done'
        and row.get('status') == 'completed'
        and not any(
            row.get(key)
            for key in ('home_hidden', 'backfilled', 'is_locked', 'sync_merged_into', 'deleted', 'discarded')
        )
        and present(row.get('structured'))
    )


def eligible_after(before: Mapping[str, object], after: Mapping[str, object], *, rewritten: bool, visible) -> bool:
    """Whether a committed write made a Finish window eligible: newly, or with notes it just rewrote."""
    return enabled() and home_ready(after) and visible(after) and (rewritten or not home_ready(before))


def observe_home_summary(uid, row):
    """Validation only: a Home response actually carried this summary to the reader."""
    if enabled() and home_ready(row):
        observe_summary(uid, row['id'])


def observe_home_summaries(uid, rows) -> None:
    """Record qualifying rows from the already projected Home response."""
    for row in rows:
        observe_home_summary(uid, row)
