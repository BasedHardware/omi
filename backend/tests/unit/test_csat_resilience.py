from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import AlreadyExists, Conflict

from database import csat


class FakeDocSnapshot:
    def __init__(self, exists: bool, data: dict | None = None):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


def test_get_product_config_defaults_on_missing_doc():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeDocSnapshot(False, None)
    client.collection.return_value.document.return_value = doc_ref

    cfg = csat.get_product_config(firestore_client=client)
    assert cfg['enabled'] is True
    assert cfg['title'] == csat.DEFAULT_TITLE
    assert cfg['question_threshold'] == 3
    assert cfg['comment_max_score'] == 3
    assert cfg['revision'] == 0


def test_get_product_config_safe_on_storage_exception():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.side_effect = RuntimeError('Firestore read error')
    client.collection.return_value.document.return_value = doc_ref

    cfg = csat.get_product_config(firestore_client=client)
    assert cfg['enabled'] is True
    assert cfg['title'] == csat.DEFAULT_TITLE


def test_get_product_config_normalizes_corrupted_doc():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = FakeDocSnapshot(
        True,
        {
            'enabled': False,
            'title': '   ',
            'question_threshold': 999,
            'comment_max_score': -10,
            'revision': -5,
        },
    )
    client.collection.return_value.document.return_value = doc_ref

    cfg = csat.get_product_config(firestore_client=client)
    assert cfg['enabled'] is False
    assert cfg['title'] == csat.DEFAULT_TITLE  # Whitespace falls back to default
    assert cfg['question_threshold'] == 50  # Clamped to 50
    assert cfg['comment_max_score'] == 1  # Clamped to 1
    assert cfg['revision'] == 0  # Negative clamped to 0


def test_submit_rating_valid():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    doc_id, created = csat.submit_rating(
        uid='user_123',
        platform='macos',
        app_version='1.5.0',
        score=2,
        comment='Needs dark mode',
        revision=1,
        firestore_client=client,
    )

    assert doc_id == 'macos_user_123'
    assert created is True
    client.collection.assert_called_with(csat.RATINGS_COLLECTION)
    client.collection.return_value.document.assert_called_with('macos_user_123')
    payload = doc_ref.create.call_args[0][0]
    assert payload['uid'] == 'user_123'
    assert payload['platform'] == 'macos'
    assert payload['app_version'] == '1.5.0'
    assert payload['score'] == 2
    assert payload['comment'] == 'Needs dark mode'
    assert payload['revision'] == 1
    assert payload['created_at'] > 0


def test_submit_rating_truncates_long_comment():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    long_comment = 'A' * 1000
    doc_id, created = csat.submit_rating(
        uid='user_123',
        platform='ios',
        app_version='2.0.0',
        score=1,
        comment=long_comment,
        revision=0,
        firestore_client=client,
    )

    payload = doc_ref.create.call_args[0][0]
    assert len(payload['comment']) == csat.MAX_COMMENT_LENGTH
    assert payload['comment'] == 'A' * csat.MAX_COMMENT_LENGTH


def test_submit_rating_drops_comment_when_score_above_max():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    doc_id, created = csat.submit_rating(
        uid='user_123',
        platform='windows',
        app_version='1.0.0',
        score=5,
        comment='Great app!',
        revision=0,
        firestore_client=client,
    )

    payload = doc_ref.create.call_args[0][0]
    assert payload['comment'] == ''


def test_submit_rating_conflict_handling():
    client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.create.side_effect = AlreadyExists('Document already exists')
    client.collection.return_value.document.return_value = doc_ref

    doc_id, created = csat.submit_rating(
        uid='user_123',
        platform='android',
        app_version='1.0.0',
        score=3,
        comment='',
        revision=0,
        firestore_client=client,
    )

    assert doc_id == 'android_user_123'
    assert created is False


@pytest.mark.parametrize('bad_uid', ['', '  ', None, 123, 'users/traversal/sub', 'path/id'])
def test_submit_rating_invalid_uid_rejected(bad_uid):
    client = MagicMock()
    with pytest.raises(ValueError, match='Invalid uid'):
        csat.submit_rating(
            uid=bad_uid,
            platform='macos',
            app_version='1.0.0',
            score=3,
            comment='',
            revision=0,
            firestore_client=client,
        )


@pytest.mark.parametrize('bad_platform', ['', '  ', None, 'web', 'linux', 'MACOS/attack'])
def test_submit_rating_invalid_platform_rejected(bad_platform):
    client = MagicMock()
    with pytest.raises(ValueError, match='[Pp]latform'):
        csat.submit_rating(
            uid='user_123',
            platform=bad_platform,
            app_version='1.0.0',
            score=3,
            comment='',
            revision=0,
            firestore_client=client,
        )


@pytest.mark.parametrize('bad_score', [0, 6, -1, 10, 'high', None])
def test_submit_rating_invalid_score_rejected(bad_score):
    client = MagicMock()
    with pytest.raises(ValueError, match='Score'):
        csat.submit_rating(
            uid='user_123',
            platform='macos',
            app_version='1.0.0',
            score=bad_score,
            comment='',
            revision=0,
            firestore_client=client,
        )
