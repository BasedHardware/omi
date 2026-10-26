from types import SimpleNamespace
import uuid

import pytest

from utils import live_speaker_suggestions as events


@pytest.mark.parametrize(
    'person,retracted,owner', [('user', False, True), ('p1', False, False), ('', True, False), ('user', True, False)]
)
def test_explicit_owner_bit_and_legacy_sentinel(monkeypatch, person, retracted, owner):
    emitted = []
    monkeypatch.setattr(events, 'emit_product_event', lambda **k: None)
    host = SimpleNamespace(
        request=SimpleNamespace(uid=str(uuid.uuid4()), speaker_auto_assign_enabled=True),
        state=SimpleNamespace(current_conversation_id='c'),
        recording_session_id='r',
        send_event=emitted.append,
    )
    events.emit_speaker_suggestion(host, 1, person, '', 's', retracted=retracted)
    wire = emitted[0].to_json()
    assert wire['is_user'] is owner
    if owner:
        assert wire['person_id'] == 'user'
    if retracted:
        assert wire['retracted'] is True
