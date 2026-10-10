"""Independent review regressions through authority, storage and webhook sinks."""

import asyncio
import json
import zlib
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversations as db
from models.conversation import Conversation
from models.transcript_segment import GROUPING_INTERNAL_FIELDS, transcript_segment_for_client
from tests.unit.test_speaker_grouping_shadow import conversation, segment
from utils import encryption, app_integrations as apps, webhooks
from utils.conversations import speaker_grouping_shadow as shadow, speaker_grouping_storage as storage
from utils.conversations.render import (
    conversation_to_dict,
    redact_conversation_for_integration,
    redact_conversation_for_list,
)
from utils.conversations.speaker_resolution import apply_speaker_resolution
from utils.stt.conversation_speakers import resolve_conversation_speakers


@pytest.mark.parametrize('shadow_mode', ['off', 'owner'])
def test_owner_link_config_never_reaches_authoritative_projection(monkeypatch, shadow_mode):
    monkeypatch.setenv('SPEAKER_GROUPING_MODE', 'owner_link')
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', shadow_mode)
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST', 'owner')
    c = conversation([segment(0), segment(1, 'live:b')])
    vectors = {'0': [0.7, 0.714142842854285], '1': [0.7, -0.714142842854285]}
    prints = {'user': [1, 0]}
    incumbent = resolve_conversation_speakers(c.transcript_segments, vectors, voiceprints=prints)
    result = shadow.compare_and_select(
        'owner',
        c,
        incumbent,
        vectors,
        manual_speakers={},
        voiceprints=prints,
        embedding_seconds={'0': 8, '1': 8},
        abstained_segment_ids=set(),
        receipt={},
    )
    assert result is incumbent
    apply_speaker_resolution(
        c,
        result.speaker_ids,
        result.voice_identities,
        result.voice_identity_statuses,
        owner_voiceprint_available=result.owner_voiceprint_available,
    )
    assert all(not s.is_user for s in c.transcript_segments)
    if shadow_mode == 'owner':
        assert all(s.speaker_grouping_shadow['owner_link'] == 'user' for s in c.transcript_segments)


def internal_conversation(level):
    s = segment(0)
    s.assign_resolved_speaker(55, 'conversation:c')
    s.speaker_grouping_shadow = {'provider_strict': 'person:private-person', 'owner_link': 'user'}
    c = conversation([s])
    c.data_protection_level = level
    return c


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_storage_always_encrypts_internal_evidence_and_preserves_scoped_partition(level):
    c = internal_conversation(level)
    stored = db.encode_conversation_for_write('owner', c.model_dump(), level)
    transcript = db._reveal_json_value(stored['transcript_segments'], 'owner', True)
    assert not (set(GROUPING_INTERNAL_FIELDS) - {storage.FIELD}) & set(transcript[0])
    assert 'private-person' not in json.dumps(transcript)
    assert 'live:a' not in json.dumps(transcript)
    envelope = json.loads(encryption.decrypt(transcript[0][storage.FIELD], 'owner'))
    assert envelope['values']['provider_speaker']['scope'] == 'live:a'
    assert envelope['values']['speaker_grouping_shadow']['provider_strict'] == 'person:private-person'
    stored['data_protection_level'] = level
    restored = Conversation(**db.prepare_conversation_for_read(stored, 'owner'))
    assert shadow.provider_key(restored.transcript_segments[0]) == ('soniox\0live:a', 0)
    restored.transcript_segments[0].assign_resolved_speaker(70, 'conversation:c')
    assert shadow.provider_key(restored.transcript_segments[0]) == ('soniox\0live:a', 0)


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
def test_protection_migration_keeps_evidence_encrypted(source, target):
    c = internal_conversation(source)
    first = db.encode_conversation_for_write('owner', c.model_dump(), source)
    first['data_protection_level'] = source
    decoded = db.prepare_conversation_for_read(first, 'owner')
    expiry = decoded['transcript_segments'][0]['speaker_grouping_shadow_expires_at']
    migrated = db.encode_conversation_for_write('owner', decoded, target)
    migrated['data_protection_level'] = target
    rows = db._reveal_json_value(migrated['transcript_segments'], 'owner', True)
    assert 'speaker_grouping_shadow' not in rows[0] and 'provider_speaker' not in rows[0]
    restored = db.prepare_conversation_for_read(migrated, 'owner')['transcript_segments'][0]
    assert restored['speaker_grouping_shadow_expires_at'] == expiry
    assert restored['speaker_grouping_shadow'] == c.transcript_segments[0].speaker_grouping_shadow


def test_storage_failure_expiry_bounds_and_wrong_owner_drop_optional_evidence(monkeypatch):
    c = internal_conversation('standard')
    stored = db.encode_conversation_for_write('owner', c.model_dump())
    wrong = db.prepare_conversation_for_read(stored, 'different-owner')['transcript_segments'][0]
    assert not set(GROUPING_INTERNAL_FIELDS) & set(wrong)
    monkeypatch.setattr(storage.time, 'time', lambda: 10**12)
    expired = db.prepare_conversation_for_read(stored, 'owner')['transcript_segments'][0]
    assert 'provider_speaker' in expired and 'speaker_grouping_shadow' not in expired
    monkeypatch.setattr(encryption, 'encrypt', lambda *a: (_ for _ in ()).throw(ValueError('failed')))
    failed = db.encode_conversation_for_write('owner', c.model_dump())
    assert not set(GROUPING_INTERNAL_FIELDS) & set(json.loads(zlib.decompress(failed['transcript_segments']))[0])
    monkeypatch.undo()
    monkeypatch.setattr(storage, 'MAX_BYTES', 1)
    limited = db.encode_conversation_for_write('owner', c.model_dump())
    assert not set(GROUPING_INTERNAL_FIELDS) & set(json.loads(zlib.decompress(limited['transcript_segments']))[0])


def test_epoch_and_renumbered_partition_survive_reprocessing():
    segments = [segment(0, 'epoch:a', 43), segment(1, 'epoch:a', 44), segment(2, 'epoch:b', 43)]
    c = conversation(segments)
    vectors = {s.id: [1, 0] for s in segments}
    original = {s.id: shadow.provider_key(s) for s in segments}
    for s in segments:
        s.assign_resolved_speaker(0, 'conversation:c')
    for _ in range(2):
        stored = db.encode_conversation_for_write('owner', c.model_dump())
        stored['data_protection_level'] = 'standard'
        c = Conversation(**db.prepare_conversation_for_read(stored, 'owner'))
        keys = {s.id: shadow.provider_key(s) for s in c.transcript_segments}
        assert keys == original
        result = resolve_conversation_speakers(
            c.transcript_segments, vectors, grouping='provider_strict', provider_keys=keys
        )
        assert result.speaker_ids['0'] != result.speaker_ids['1']
        apply_speaker_resolution(
            c,
            result.speaker_ids,
            result.voice_identities,
            result.voice_identity_statuses,
            owner_voiceprint_available=result.owner_voiceprint_available,
        )


@pytest.mark.parametrize('fault', ['unserializable', 'plaintext_sidecar', 'encrypt_returns_plaintext'])
def test_storage_never_falls_back_to_plaintext_or_blocks_transcript(monkeypatch, fault):
    row = segment(0).model_dump()
    if fault == 'unserializable':
        row['provider_speaker'] = {'bad': object()}
    elif fault == 'plaintext_sidecar':
        row[storage.FIELD] = json.dumps(
            {'id': row['id'], 'values': {'speaker_grouping_shadow': {'owner_link': 'user'}}}
        )
    else:
        row['speaker_grouping_shadow'] = {'owner_link': 'user'}
        monkeypatch.setattr(encryption, 'encrypt', lambda payload, uid: payload)
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [row]})
    restored = json.loads(zlib.decompress(stored['transcript_segments']))[0]
    assert restored['text'] == 'private words'
    assert not set(GROUPING_INTERNAL_FIELDS) & set(restored)


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_public_raw_dictionary_projections_remove_all_internal_fields(level):
    c = internal_conversation(level)
    raw = c.model_dump()
    raw['transcript_segments'][0][storage.FIELD] = 'encrypted-internal-sidecar'
    for sink in (redact_conversation_for_integration, redact_conversation_for_list):
        result = sink(deepcopy(raw))
        assert not set(GROUPING_INTERNAL_FIELDS) & set(result['transcript_segments'][0])
    assert not set(GROUPING_INTERNAL_FIELDS) & set(conversation_to_dict(c)['transcript_segments'][0])
    assert not set(GROUPING_INTERNAL_FIELDS) & set(transcript_segment_for_client(raw['transcript_segments'][0]))


@pytest.mark.asyncio
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
async def test_actual_app_and_developer_webhook_payloads_are_public(monkeypatch, level):
    c = internal_conversation(level)
    stored = db.encode_conversation_for_write('owner', c.model_dump(), level)
    stored['data_protection_level'] = level
    c = Conversation(**db.prepare_conversation_for_read(stored, 'owner'))
    payloads = []

    async def blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def post(*args, **kwargs):
        payloads.append(kwargs['json'])
        return SimpleNamespace(status_code=200, json=lambda: {})

    cb = MagicMock()
    cb.allow_request.return_value = True
    monkeypatch.setattr(apps, 'run_blocking', blocking)
    app = SimpleNamespace(
        id='app',
        name='Synthetic app',
        uid='owner',
        enabled=True,
        triggers_on_conversation_creation=lambda: True,
        triggers_realtime=lambda: True,
        external_integration=SimpleNamespace(webhook_url='https://synthetic.example/hook'),
    )
    monkeypatch.setattr(apps, 'get_available_apps', lambda _: [app])
    monkeypatch.setattr(apps, 'is_app_webhook_disabled', lambda _: False)
    monkeypatch.setattr(apps, 'record_app_webhook_success', lambda _: None)
    monkeypatch.setattr(apps, 'safe_request_target', lambda url: (url, {'headers': {}, 'extensions': {}}))
    monkeypatch.setattr(apps, 'get_webhook_circuit_breaker', lambda _: cb)
    monkeypatch.setattr(apps, 'get_webhook_semaphore', lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(apps, 'get_webhook_client', lambda: SimpleNamespace(post=post))
    await apps.trigger_external_integrations('owner', c, require_delivery=True)
    monkeypatch.setattr(webhooks, 'run_blocking', blocking)
    monkeypatch.setattr(webhooks, 'user_webhook_status_db', lambda *a: True)
    monkeypatch.setattr(webhooks, 'get_user_webhook_db', lambda *a: 'https://synthetic.example/hook')
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', lambda *a: None)
    monkeypatch.setattr(webhooks, 'populate_speaker_names', lambda *a: None)
    monkeypatch.setattr(webhooks, 'populate_folder_names', lambda *a: None)
    monkeypatch.setattr(webhooks, 'get_webhook_circuit_breaker', lambda _: cb)
    monkeypatch.setattr(webhooks, '_post_dev_webhook', post)
    await webhooks.conversation_created_webhook('owner', c)
    monkeypatch.setattr(apps, 'is_trial_paywalled', lambda *a: False)
    monkeypatch.setenv('MENTOR_PIPELINE', 'off')
    raw_segments = [s.model_dump() for s in c.transcript_segments]
    raw_segments[0][storage.FIELD] = 'encrypted-internal-sidecar'
    await apps.trigger_realtime_integrations('owner', raw_segments, c.id)
    await webhooks.realtime_transcript_webhook('owner', raw_segments)
    assert len(payloads) == 4
    for payload in payloads:
        rows = payload.get('transcript_segments', payload.get('segments'))
        assert not set(GROUPING_INTERNAL_FIELDS) & set(rows[0])
        assert 'private-person' not in json.dumps(payload)
        assert rows[0]['text'] == 'private words'
    assert raw_segments[0]['speaker_grouping_shadow']
