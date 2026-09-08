from database.helpers import with_photos


def test_with_photos_skips_empty_subcollection_read_for_authoritative_false_marker():
    calls = []

    @with_photos(lambda **kwargs: calls.append(kwargs) or [{'id': 'unexpected'}])
    def load(uid):
        return {'id': 'conversation-1', 'has_photos': False}

    assert load('user-1') == {'id': 'conversation-1', 'has_photos': False, 'photos': []}
    assert calls == []


def test_with_photos_preserves_legacy_lookup_when_marker_is_absent():
    calls = []

    @with_photos(lambda **kwargs: calls.append(kwargs) or [{'id': 'photo-1'}])
    def load(uid):
        return {'id': 'legacy-conversation'}

    assert load('user-1')['photos'] == [{'id': 'photo-1'}]
    assert calls == [{'uid': 'user-1', 'conversation_id': 'legacy-conversation'}]


def test_with_photos_loads_when_marker_is_true():
    calls = []

    @with_photos(lambda **kwargs: calls.append(kwargs) or [{'id': 'photo-1'}])
    def load(uid):
        return {'id': 'conversation-1', 'has_photos': True}

    assert load('user-1')['photos'] == [{'id': 'photo-1'}]
    assert calls == [{'uid': 'user-1', 'conversation_id': 'conversation-1'}]
