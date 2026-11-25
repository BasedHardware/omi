"""Pin typed equality and the protected storage representations a projection may skip."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from uuid import uuid4
import zlib

import pytest
import yaml
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.cloud import firestore

from config.conversations_v3 import skip_unchanged_writes_enabled
from database import conversations_v3_write_equality as equality
from utils.encryption import encrypt
from utils.home_feed.projection import SCHEMA, reveal_display


@pytest.mark.parametrize(
    ('before', 'after', 'equal'),
    [
        ({'a': 1, 'b': [2.0]}, {'b': [2.0], 'a': 1}, True),
        (True, 1, False),
        (1, 1.0, False),
        (-0.0, 0.0, False),
        (float('nan'), float('nan'), True),
        ([1, 2], [2, 1], False),
        (
            datetime(2026, 11, 25, tzinfo=timezone.utc),
            datetime(2026, 11, 24, 19, tzinfo=timezone(-timedelta(hours=5))),
            True,
        ),
        (
            DatetimeWithNanoseconds(2026, 11, 25, tzinfo=timezone.utc, nanosecond=1001),
            datetime(2026, 11, 25, tzinfo=timezone.utc, microsecond=1),
            False,
        ),
        (firestore.SERVER_TIMESTAMP, firestore.SERVER_TIMESTAMP, False),
        ({'a': firestore.DELETE_FIELD}, {'a': firestore.DELETE_FIELD}, False),
    ],
)
def test_storage_value_equality(before, after, equal):
    assert equality.same_value(before, after) is equal


def test_missing_fields_and_transforms_are_not_equal_patches():
    assert not equality.same_patch({}, {'a': None})
    assert not equality.same_patch({}, {'a': firestore.DELETE_FIELD})
    assert not equality.same_patch({'a': None}, {'a': firestore.SERVER_TIMESTAMP})
    assert equality.same_patch({'a': None, 'other': 12}, {'a': None})
    assert not equality.same_patch({'a.b': 1, 'a': {'b': 2}}, {'a.b': 1})


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_projected_storage_compares_protected_content_without_losing_real_changes(level):
    uid = 'synthetic'

    def row(display, speaker=1):
        compressed = zlib.compress(json.dumps([{'speaker': speaker, 'text': 'hi'}]).encode())
        return {
            'data_protection_level': level,
            'transcript_segments_compressed': True,
            'transcript_segments': encrypt(compressed.hex(), uid) if level == 'enhanced' else compressed,
            'structured': {'title': 'Hi'},
            'home_display': encrypt(json.dumps({**json.loads(display), 'schema': SCHEMA}), uid),
            'home_display_version': uuid4().hex,
        }

    before = {**row('{"a":1,"b":2}'), 'home_source_version': uuid4().hex, 'home_content_invalidated': False}
    after = row('{"b":2,"a":1}')
    assert equality.same_conversation(uid, before, after)
    assert not equality.same_conversation(uid, before, row('{"b":2,"a":1}', speaker=2))
    assert not equality.same_conversation(uid, before, row('{"b":3,"a":1}'))
    assert not equality.same_conversation(uid, {**before, 'home_content_invalidated': True}, after)
    # The planner can carry both commit stamps from its prior row. A real write
    # still resets an inherited invalidation bit once structured content exists.
    invalidated = {**before, 'home_content_invalidated': True}
    assert not equality.same_conversation(uid, invalidated, invalidated)
    assert not equality.same_conversation(uid, {**before, 'obsolete': None}, after)
    assert not equality.same_conversation(uid, before, {**after, 'data_protection_level': 'private'})
    assert not equality.same_conversation(uid, before, {**after, 'transcript_segments': {'path': 'different-pointer'}})


def test_sync_scrape_keeps_projection_histograms():
    config = yaml.safe_load((Path(__file__).parents[2] / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    relabeling = config['spec']['endpoints'][0]['metricRelabeling']
    for metric in ('omi_conversations_v3_projection_rows', 'omi_conversations_v3_reconcile_billed_writes'):
        for suffix in ('bucket', 'count', 'sum'):
            assert any(
                rule['action'] == 'keep' and re.fullmatch(rule['regex'], f'{metric}_{suffix}') for rule in relabeling
            )


@pytest.mark.parametrize('value', ['off', 'false', 'no', '0'])
def test_write_elision_uses_standard_kill_switch_values(monkeypatch, value):
    monkeypatch.setenv('CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES', value)
    assert not skip_unchanged_writes_enabled()


def test_home_display_must_be_servable_even_when_the_stored_field_matches():
    uid = 'synthetic'
    display = {'schema': SCHEMA, 'title': 'same'}
    planned = {'home_display': encrypt(json.dumps(display), uid)}
    oversized = encrypt(' ' * 7000 + json.dumps(display), uid)

    assert reveal_display(uid, planned['home_display']) == display
    for unreadable in (oversized, json.dumps(display)):
        assert reveal_display(uid, unreadable) is None
        stored = {'home_display': unreadable}
        assert not equality.same_conversation(uid, stored, planned)
        assert not equality.same_conversation(uid, stored, stored)
