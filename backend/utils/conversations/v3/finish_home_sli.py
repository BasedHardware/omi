"""Content-free, kill-switch-gated observations for deliberate v3 Finishes."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
from uuid import UUID

from config.app_channel import APP_CHANNEL_HEADER, app_channel
from config.conversations_v3 import conversations_v3_enabled
from utils.encryption import ENCRYPTION_SECRET

_logger = logging.getLogger(__name__)
HEADER = 'X-Omi-Finish-Cut'


def enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_FINISH_HOME_SLI', '').strip().lower() == 'on'


def _key(kind: str, uid: str, identifier: str) -> str:
    raw = json.dumps([kind, uid, identifier], separators=(',', ':')).encode()
    return hmac.new(ENCRYPTION_SECRET, b'v3-finish-home-sli:' + raw, hashlib.sha256).hexdigest()[:32]


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

    def bind(self, recording_id: str) -> None:
        if self.finish is None:
            # Released clients without the header carry no source or device cut
            # clock. A recording key deduplicates the observable server cut.
            finish = _key('legacy-finish', self.uid, recording_id)
            Finish(self.uid, finish, self.cut_at, self.source, self.basis).cut()
        else:
            finish = self.finish
        _emit('binding', finish=finish, recording=_key('recording', self.uid, recording_id))


def from_request(uid: str, request) -> Finish | None:
    if not enabled() or request is None:
        return None
    header = request.headers.get(HEADER, '')
    if header == 'none' or len(header) > 100:
        return None
    if app_channel(request.headers.get(APP_CHANNEL_HEADER)) != 'beta' or not conversations_v3_enabled(uid):
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
    if enabled() and route in {'fast', 'batch', 'held'}:
        _emit('route', recording=_key('recording', uid, recording_id), route=route)


def observe_window(uid: str, recording_id: str, card_id: str) -> None:
    if enabled():
        _emit('window', recording=_key('recording', uid, recording_id), card=_key('card', uid, card_id))


def observe_summary(uid: str, card_id: str) -> None:
    if enabled():
        _emit('summary', card=_key('card', uid, card_id))


def observe_home_summary(uid, row):
    """Validate a settled notes row against the v3 Home list's visibility contract."""
    if not enabled():
        return
    from database.conversations import is_visible_conversation
    from utils.conversations.fragment_visibility import is_relevance_discarded
    from utils.conversations.summary_delivery import present

    if (
        row.get('v3_derived')
        and row.get('manual_end')
        and row.get('v3_notes_written')
        and row.get('tile_state') == 'done'
        and row.get('status') == 'completed'
        and not row.get('backfilled')
        and not row.get('is_locked')
        and not row.get('sync_merged_into')
        and not is_relevance_discarded(row)
        and is_visible_conversation(row, hide_home=True, presentation=True)
        and present(row.get('structured'))
    ):
        observe_summary(uid, row['id'])
