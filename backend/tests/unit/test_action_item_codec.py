"""Unit tests for database.action_item_codec — read-path immutability,
date normalization boundaries, status stripping, and provenance defense."""

from datetime import datetime, timezone

from database.action_item_codec import (
    prepare_action_item_for_read,
    prepare_action_item_for_write,
)


class TestWritePath:
    def test_status_whitespace_stripped(self):
        out = prepare_action_item_for_write({'status': '  completed  '})
        assert out['status'] == 'completed'

    def test_blank_status_falls_to_inference(self):
        out = prepare_action_item_for_write({'status': '   ', 'completed': True})
        assert out['status'] == 'completed'

    def test_provenance_coerced_when_nonlist(self):
        out = prepare_action_item_for_write({'provenance': 'not-a-list'})
        assert out['provenance'] == []

    def test_provenance_preserved_when_list(self):
        out = prepare_action_item_for_write({'provenance': ['a']})
        assert out['provenance'] == ['a']

    def test_write_normalizes_iso_due_at(self):
        out = prepare_action_item_for_write({'due_at': '2026-01-15T10:00:00Z'})
        assert out['due_at'] == datetime(2026, 1, 15, 10, tzinfo=timezone.utc)

    def test_write_drops_malformed_date(self):
        out = prepare_action_item_for_write({'due_at': 'not-a-date'})
        assert 'due_at' not in out

    def test_write_rejects_status_completed_disagreement(self):
        import pytest

        with pytest.raises(ValueError, match='completed must agree'):
            prepare_action_item_for_write({'status': 'completed', 'completed': False})


class TestReadImmutability:
    def test_read_never_mutates_input(self):
        src = {'status': 'active'}
        prepare_action_item_for_read(src)
        assert 'completed' not in src
        assert src == {'status': 'active'}

    def test_read_copies_before_defaults(self):
        src = {}
        out = prepare_action_item_for_read(src)
        assert src == {}
        assert out['status'] == 'active'


class TestReadDateBoundary:
    def test_read_parses_iso_string(self):
        out = prepare_action_item_for_read({'due_at': '2026-03-01T08:00:00Z'})
        assert out['due_at'] == datetime(2026, 3, 1, 8, tzinfo=timezone.utc)

    def test_read_coerces_timestamp_objects(self):
        class _Ts:
            def timestamp(self):
                return 1700000000

        out = prepare_action_item_for_read({'created_at': _Ts()})
        assert out['created_at'] == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    def test_read_coerces_to_datetime_objects(self):
        class _Fs:
            def to_datetime(self):
                return datetime(2025, 5, 5, tzinfo=timezone.utc)

        out = prepare_action_item_for_read({'updated_at': _Fs()})
        assert out['updated_at'] == datetime(2025, 5, 5, tzinfo=timezone.utc)

    def test_read_survives_unparseable_date(self):
        class _Bad:
            @property
            def timestamp(self):
                raise OSError('clock failed')

        out = prepare_action_item_for_read({'due_at': _Bad()})
        assert 'due_at' in out  # degraded, not raised

    def test_read_naive_datetime_gets_utc(self):
        out = prepare_action_item_for_read({'due_at': datetime(2026, 1, 1, 12)})
        assert out['due_at'].tzinfo == timezone.utc


class TestReadDefaults:
    def test_null_completed_derives_from_status(self):
        out = prepare_action_item_for_read({'status': 'completed', 'completed': None})
        assert out['completed'] is True

    def test_missing_status_infers_active(self):
        out = prepare_action_item_for_read({})
        assert out['status'] == 'active'
        assert out['completed'] is False

    def test_defaults_injected(self):
        out = prepare_action_item_for_read({})
        for k in ('owner', 'source', 'provenance', 'sort_order', 'indent_level'):
            assert k in out


class TestReadResponseShape:
    def test_iso_string_in_returns_aware_datetime(self):
        """Read normalization: ISO-string input must come back as an aware
        datetime — the API-visible shape change is intentional."""
        out = prepare_action_item_for_read({'due_at': '2026-03-04T15:30:00Z'})
        assert isinstance(out['due_at'], datetime)
        assert out['due_at'].tzinfo is not None
        assert out['due_at'] == datetime(2026, 3, 4, 15, 30, tzinfo=timezone.utc)
