"""Operator safety at the actual codec, CAS adapter and private-ledger boundaries."""

from copy import deepcopy
import ctypes.util
from datetime import datetime, timedelta, timezone
import importlib
import os
from pathlib import Path
import stat
from types import SimpleNamespace

from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import LastUpdateOption
import pytest

from scripts import capture_empty_recovery as cli
from utils.conversations import empty_capture_recovery as recovery


@pytest.fixture
def codec(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-empty-capture-test-key-1234567890')
    encryption = importlib.import_module('utils.encryption')
    monkeypatch.setattr(encryption, 'ENCRYPTION_SECRET', b'synthetic-empty-capture-test-key-1234567890')
    encryption.clear_derived_key_cache()
    module = importlib.import_module('database.capture_speech')
    yield SimpleNamespace(encryption=encryption, decode=module.decode_capture_segments)
    encryption.clear_derived_key_cache()


def candidate(codec, *, duration=90, level='standard', segments=None, title='Recording · 3:14 PM'):
    row = {
        'status': 'completed',
        'finalization_status': 'dead_letter',
        'discarded': False,
        'data_protection_level': level,
        'transcript_segments_compressed': True,
        'transcript_segments': cli.encode_segments(codec, 'synthetic-owner', segments or [], level),
        'user_corrections': cli.encode_segments(codec, 'synthetic-owner', [], level),
        'user_corrections_compressed': True,
        'structured': {'title': title, 'overview': '', 'sections': [], 'emoji': '💬', 'category': 'other'},
        'audio_files': [{'duration': duration}],
    }
    return recovery.Observed('synthetic-owner', 'synthetic-capture', row, datetime(2026, 10, 31, tzinfo=timezone.utc))


class CAS:
    """A document precondition model, not a permissive transaction fake."""

    def __init__(self, observed):
        self.current = deepcopy(observed)
        self.writes = []

    def __call__(self, observed, patch):
        if observed.revision != self.current.revision:
            raise recovery.Changed()
        self.current.row.update(deepcopy(patch))
        self.current.revision += timedelta(microseconds=1)
        self.writes.append(deepcopy(patch))
        return self.current.revision


def reprocess(codec, observed, cas, provider, **kwargs):
    return recovery.reprocess_one(
        observed,
        decode=codec.decode,
        encode=lambda uid, segments, level: cli.encode_segments(codec, uid, segments, level),
        cas=cas,
        transcribe=provider,
        **kwargs,
    )


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_real_codec_fill_preserves_title_and_rerun_never_calls_provider(codec, level):
    observed = candidate(codec, level=level)
    before = deepcopy(observed.row)
    cas = CAS(observed)
    calls = []
    segments = [{'text': 'Synthetic fixture.', 'start': 2.0, 'end': 3.0}]
    assert reprocess(codec, observed, cas, lambda row: calls.append(row) or segments) == 'filled'
    assert codec.decode(observed.uid, cas.current.row['transcript_segments'], True) == segments
    assert cas.current.row['structured'] == before['structured']
    assert set(cas.writes[-1]) == {'transcript_segments', 'transcript_segments_compressed', recovery.MARKER}
    assert isinstance(cas.current.row['transcript_segments'], str if level == 'enhanced' else bytes)
    assert reprocess(codec, cas.current, cas, lambda _: pytest.fail('duplicate paid call')) == 'already_attempted'
    assert len(calls) == 1


@pytest.mark.parametrize(
    'change',
    [
        {'user_title': 'Synthetic user edit'},
        {'has_transcript_corrections': True},
        {'transcript_correction_overlay': {}},
        {'manual_speaker_assignments': {'synthetic': 'manual'}},
        {'structured': {'title': 'Synthetic title'}},
        {'structured': {'title': 'Recording · 3:14 PM', 'overview': 'Synthetic user summary'}},
        {'sync_relevance_user_kept': True},
        {'starred': True},
        {'has_photos': True},
    ],
)
def test_protected_rows_are_never_changed(codec, change):
    observed = candidate(codec)
    observed.row.update(change)
    cas = CAS(observed)
    reprocess(codec, observed, cas, lambda _: pytest.fail('protected row reached STT'))
    assert cas.writes == []


def test_nonempty_transcript_is_never_overwritten(codec):
    observed = candidate(codec, segments=[{'text': 'Synthetic original.', 'start': 0, 'end': 1}])
    cas = CAS(observed)
    assert reprocess(codec, observed, cas, lambda _: pytest.fail('nonempty reached STT')) == 'nonempty_transcript'
    assert cas.writes == []


def test_row_changed_before_claim_never_calls_provider(codec):
    observed = candidate(codec)
    cas = CAS(observed)
    cas.current.revision += timedelta(seconds=1)
    cas.current.row['user_title'] = 'Synthetic concurrent title'
    assert reprocess(codec, observed, cas, lambda _: pytest.fail('lost claim reached STT')) == 'row_changed'
    assert cas.writes == []


def test_row_changed_during_provider_preserves_concurrent_transcript(codec):
    observed = candidate(codec, level='enhanced')
    cas = CAS(observed)
    concurrent = [{'text': 'Synthetic concurrent transcript.', 'start': 0, 'end': 1}]

    def provider(_):
        cas.current.row['transcript_segments'] = cli.encode_segments(codec, observed.uid, concurrent, 'enhanced')
        cas.current.revision += timedelta(seconds=1)
        return [{'text': 'Synthetic replay.', 'start': 0, 'end': 1}]

    assert reprocess(codec, observed, cas, provider) == 'row_changed_after_claim'
    assert codec.decode(observed.uid, cas.current.row['transcript_segments'], True) == concurrent
    assert len(cas.writes) == 1


def test_uncertain_provider_is_not_retried(codec):
    observed = candidate(codec)
    cas = CAS(observed)

    def fail(_):
        raise RuntimeError('synthetic provider failure')

    assert reprocess(codec, observed, cas, fail) == 'reprocess_unproven'
    assert reprocess(codec, cas.current, cas, lambda _: pytest.fail('uncertain call retried')) == 'already_attempted'


def test_enhanced_unknown_ciphertext_is_unproven(codec):
    observed = candidate(codec, level='enhanced')
    observed.row['transcript_segments'] = 'not-authenticated'
    cas = CAS(observed)
    assert (
        reprocess(codec, observed, cas, lambda _: pytest.fail('unverified blob reached STT')) == 'transcript_unproven'
    )
    assert not cas.writes


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_only_verified_empty_protected_correction_list_passes(codec, level):
    observed = candidate(codec, level=level)
    assert recovery.classify(observed, codec.decode) == 'reprocess_long'
    observed.row['user_corrections'] = cli.encode_segments(codec, observed.uid, [{'text': 'Synthetic edit'}], level)
    assert recovery.classify(observed, codec.decode) == 'protected_content'
    observed.row['user_corrections'] = 'corrupt-correction-blob'
    assert recovery.classify(observed, codec.decode) == 'protected_content'


def test_bare_shell_missing_transcript_is_reprocess_only(codec):
    observed = candidate(codec, title='', duration=20)
    observed.row.pop('transcript_segments')
    assert recovery.classify(observed, codec.decode) == 'reprocess_shell'
    cas = CAS(observed)
    assert recovery.hide_one(observed, 0, decode=codec.decode, cas=cas, ledger=None) == 'reprocess_shell'
    assert not cas.writes


def test_short_reprocess_requires_measured_speech(codec):
    observed = candidate(codec, duration=20)
    cas = CAS(observed)
    assert reprocess(codec, observed, cas, lambda _: pytest.fail('unmeasured short STT')) == 'short_speech_unproven'


def test_hide_write_ahead_private_ledger_and_undo(codec, tmp_path, monkeypatch):
    root = tmp_path / 'private'
    monkeypatch.setattr(cli, 'LEDGER_ROOT', root)
    ledger = cli.Ledger(root / 'rollback.jsonl', create=True)
    observed = candidate(codec, duration=20, level='enhanced')
    cas = CAS(observed)

    def write(observed, patch):
        # The durable intent must exist before the first Firestore mutation.
        assert ledger.entries()
        return cas(observed, patch)

    try:
        assert recovery.hide_one(observed, 0, decode=codec.decode, cas=write, ledger=ledger) == 'hidden'
        assert stat.S_IMODE((root / 'rollback.jsonl').stat().st_mode) == 0o600
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert recovery.hide_one(cas.current, 0, decode=codec.decode, cas=cas, ledger=ledger) == 'already_hidden'
        entry = ledger.entries()[0]
        assert 'transcript_segments' not in entry and 'structured' not in entry
        assert recovery.undo_one(cas.current, entry, cas=cas) == 'restored'
        assert cas.current.row['discarded'] is False
        assert recovery.undo_one(cas.current, entry, cas=cas) == 'undo_not_owned'
    finally:
        ledger.close()


def test_hide_race_and_any_measured_speech_are_preserved(codec):
    observed = candidate(codec, duration=20)
    cas = CAS(observed)
    assert recovery.hide_one(observed, 0.032, decode=codec.decode, cas=cas, ledger=None) == 'measured_speech_keep'
    cas.current.revision += timedelta(seconds=1)
    ledger = SimpleNamespace(token=lambda: 'synthetic-token', prepare=lambda *_: None)
    assert recovery.hide_one(observed, 0, decode=codec.decode, cas=cas, ledger=ledger) == 'row_changed'
    assert not cas.writes


@pytest.mark.parametrize(
    'change', [{'user_title': 'Synthetic edit'}, {'deleted': True}, {'transcript_segments': ['synthetic']}]
)
def test_undo_never_restores_changed_or_deleted_row(codec, change):
    observed = candidate(codec, duration=20)
    entry = {
        'marker': {'operation': recovery.OPERATION, 'state': 'hidden', 'token': 'synthetic'},
        'before_sha256': recovery.row_digest(observed.row),
        'prior_discarded': False,
        'committed_revision': observed.revision.isoformat(),
    }
    observed.row.update(discarded=True, **{recovery.MARKER: entry['marker']})
    observed.row.update(change)
    cas = CAS(observed)
    assert recovery.undo_one(observed, entry, cas=cas) in {'deleted_or_redirected', 'undo_row_changed'}
    assert not cas.writes


def test_undo_refuses_uncertain_receipt_and_unmasked_row_change(codec):
    observed = candidate(codec, duration=20)
    marker = {'operation': recovery.OPERATION, 'state': 'hidden', 'token': 'synthetic'}
    entry = {'marker': marker, 'prior_discarded': False, 'before_sha256': recovery.row_digest(observed.row)}
    observed.row.update(discarded=True, **{recovery.MARKER: marker})
    cas = CAS(observed)
    assert recovery.undo_one(observed, entry, cas=cas) == 'undo_revision_unproven'
    entry['committed_revision'] = observed.revision.isoformat()
    observed.revision += timedelta(seconds=1)
    # The field-masked content is identical; the complete document changed.
    assert recovery.undo_one(observed, entry, cas=cas) == 'undo_row_changed'
    assert not cas.writes


@pytest.mark.parametrize(
    'failure, expected', [(FailedPrecondition, recovery.Changed), (TimeoutError, recovery.MutationUncertain)]
)
def test_cas_adapter_passes_real_sdk_precondition_and_never_retries(codec, failure, expected):
    observed = candidate(codec)
    seen = []

    def update(patch, **kwargs):
        seen.append(kwargs)
        assert isinstance(kwargs['option'], LastUpdateOption)
        assert kwargs['option']._last_update_time == observed.revision
        assert kwargs['retry'] is None
        raise failure('synthetic missing receipt')

    ref = SimpleNamespace(update=update)
    collection = SimpleNamespace(document=lambda _: ref)
    user = SimpleNamespace(collection=lambda _: collection)
    client = SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: user))
    with pytest.raises(expected):
        cli.Census(client, 0.1).cas(observed, {'discarded': True})
    assert len(seen) == 1


def test_sample_population_is_independent_of_hide_protection(codec):
    observed = candidate(codec, duration=20)
    observed.row['starred'] = True
    assert recovery.classify(observed, codec.decode) == 'protected_content'
    assert cli.sample_eligible(observed, codec.decode)


@pytest.mark.parametrize(
    'seconds, expected',
    [(0, 'zero'), (0.032, 'under_1s'), (1, '1_to_3s'), (3, '1_to_3s'), (10, '3_to_10s'), (11, 'over_10s')],
)
def test_speech_bucket_boundaries(seconds, expected):
    assert recovery.speech_bucket(seconds) == expected


@pytest.fixture
def audio_modules(codec, monkeypatch):
    # macOS strips DYLD_* across Git's hook shell. An explicit test-only
    # discovery path survives that boundary; real native codec calls remain.
    native_path = os.getenv('OMI_TEST_OPUS_LIBRARY')
    if native_path:
        assert Path(native_path).is_absolute() and Path(native_path).is_file()
        original_find = ctypes.util.find_library
        monkeypatch.setattr(
            ctypes.util, 'find_library', lambda name: native_path if name == 'opus' else original_find(name)
        )
    return SimpleNamespace(
        encryption=codec.encryption,
        timeline=importlib.import_module('database.audio_timeline'),
        source=importlib.import_module('utils.batch_pipeline.source_audio'),
        vad=importlib.import_module('utils.stt.local_vad'),
    )


def audio_store(codec, modules, level):
    observed = candidate(codec, duration=0.5, level=level)
    observed.row['audio_files'][0]['chunk_timestamps'] = [1000.0]
    opus = importlib.import_module('utils.other.audio_opus')
    pcm = bytes(16000)
    encoded = opus.encode_pcm_to_opus(pcm)
    if level == 'enhanced':
        encoded = codec.encryption.encrypt_audio_chunk(encoded, observed.uid)
    suffix = '.opus.enc' if level == 'enhanced' else '.opus'
    path = f'chunks/{observed.uid}/{observed.conversation_id}/1000.000{suffix}'
    blob = SimpleNamespace(
        name=path,
        generation=1,
        size=len(encoded),
        metadata=modules.timeline.span_blob_metadata({'start': 1000.0, 'samples': 8000, 'sample_rate': 16000}),
        reload=lambda **_: None,
        download_as_bytes=lambda **_: encoded,
    )
    bucket = SimpleNamespace(list_blobs=lambda **_: iter([blob]), blob=lambda *_, **__: blob)
    return observed, cli.Audio(SimpleNamespace(bucket=lambda _: bucket), modules), pcm


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_actual_retained_opus_decode_and_local_vad_in_memory(codec, audio_modules, level):
    observed, audio, expected = audio_store(codec, audio_modules, level)
    decoded = audio.pcm(observed)
    assert len(decoded) == len(expected)
    speech, seconds = audio.measure(observed)
    assert speech == 0 and seconds == 0.5
    assert audio.counts['object_reads'] == 2


def test_partial_retained_prefix_cannot_be_hidden(codec, audio_modules):
    observed, audio, _ = audio_store(codec, audio_modules, 'enhanced')
    observed.row['audio_files'][0]['chunk_timestamps'].append(1001.0)
    with pytest.raises(cli.Refused, match='audio_partial_missing'):
        audio.measure(observed)
    assert audio.counts['object_reads'] == 0


def test_absent_audio_manifest_cannot_prove_silence(codec, audio_modules):
    observed, audio, _ = audio_store(codec, audio_modules, 'standard')
    observed.row['audio_files'][0].pop('chunk_timestamps')
    with pytest.raises(cli.Refused, match='audio_manifest_unproven'):
        audio.measure(observed)


def test_batch_recovery_word_clocks_are_preserved(codec, audio_modules, monkeypatch):
    recognizers = importlib.import_module('utils.batch_pipeline.recovery_recognizers')

    def transcribe(item, binding, wav, **kwargs):
        assert item.duration_seconds == 5
        assert wav[:4] == b'RIFF'
        assert kwargs == {'multilingual': True}
        return {'words': [{'word': 'Synthetic fixture.', 'timestamp': [2.0, 3.0], 'speaker': 'SPEAKER_01'}]}

    monkeypatch.setattr(recognizers, 'transcribe', transcribe)
    audio = cli.Audio(None, audio_modules)
    result = audio.transcribe_pcm(bytes(5 * 32000))
    assert result[0]['start'] == 2 and result[0]['end'] == 3
    assert result[0]['speaker'] == 'SPEAKER_01'


@pytest.mark.parametrize('action', ['reprocess', 'hide'])
def test_dry_run_is_counts_only_no_provider_audio_or_writes(codec, monkeypatch, capsys, action):
    rows = [candidate(codec), candidate(codec, duration=20)]
    fake = SimpleNamespace(rows=lambda *_: iter(rows), reads={'jobs': 2, 'conversations': 2})
    monkeypatch.setattr(
        cli, 'runtime', lambda: SimpleNamespace(codec=SimpleNamespace(decode_capture_segments=codec.decode))
    )
    monkeypatch.setattr(cli, 'Census', lambda *_: fake)
    monkeypatch.setattr(cli, 'Audio', lambda *_, **__: SimpleNamespace(counts={}))
    monkeypatch.setattr(cli.firestore, 'Client', lambda **_: None)
    monkeypatch.setattr(cli.storage, 'Client', lambda **_: None)
    args = cli.parser().parse_args([action, '--after', '2026-10-29T12:00:00Z', '--before', '2026-10-30T12:00:00Z'])
    output = cli.run(args)
    text = capsys.readouterr().out
    assert output['firestore_writes'] == 0
    assert output['reprocess_base_candidates'] == 1
    assert output['hide_candidates_unmeasured'] == 1
    assert 'synthetic-owner' not in text and 'synthetic-capture' not in text
    assert 'Recording' not in text and 'transcript_segments' not in text


def test_apply_requires_explicit_caps_before_loading_credentials(monkeypatch):
    monkeypatch.setattr(cli, 'runtime', lambda: pytest.fail('invalid apply reached runtime'))
    args = cli.parser().parse_args(['hide', '--apply'])
    with pytest.raises(cli.Refused, match='explicit_serial_count_cap_required'):
        cli.run(args)


def test_ledger_prepare_failure_cannot_hide(codec):
    observed = candidate(codec, duration=20)
    cas = CAS(observed)

    def fail(*_):
        raise OSError('synthetic disk failure')

    ledger = SimpleNamespace(token=lambda: 'synthetic', prepare=fail)
    outcome = recovery.hide_one(observed, 0, decode=codec.decode, cas=cas, ledger=ledger)
    assert outcome == 'ledger_prepare_failed' and outcome in recovery.STOP_OUTCOMES
    assert not cas.writes


def test_lost_ledger_receipt_is_uncertain_not_kept(codec):
    observed = candidate(codec, duration=20)
    cas = CAS(observed)

    def fail(*_):
        raise OSError('synthetic receipt failure')

    ledger = SimpleNamespace(token=lambda: 'synthetic', prepare=lambda *_: None, committed=fail)
    outcome = recovery.hide_one(observed, 0, decode=codec.decode, cas=cas, ledger=ledger)
    assert cas.current.row['discarded'] is True
    assert outcome == 'hide_receipt_unproven' and outcome in recovery.STOP_OUTCOMES


def test_uncertain_claim_cannot_dispatch_stt(codec):
    observed = candidate(codec)
    cas = CAS(observed)

    def uncertain(observed, patch):
        cas(observed, patch)
        raise recovery.MutationUncertain()

    assert (
        reprocess(codec, observed, uncertain, lambda _: pytest.fail('uncertain claim dispatched'))
        == 'claim_commit_unproven'
    )
    assert reprocess(codec, cas.current, cas, lambda _: pytest.fail('claimed call repeated')) == 'already_attempted'


def test_synthetic_apply_stops_after_lost_hide_receipt(codec, monkeypatch):
    rows = [candidate(codec, duration=20), candidate(codec, duration=20)]
    rows[1].conversation_id = 'synthetic-second'
    stores = {row.conversation_id: CAS(row) for row in rows}
    fake = SimpleNamespace(
        rows=lambda *_: iter(rows),
        reads={'jobs': 2, 'conversations': 2},
        cas=lambda row, patch: stores[row.conversation_id](row, patch),
    )
    measured = []

    def receipt_failure(*_):
        raise OSError('synthetic ledger failure')

    ledger = SimpleNamespace(
        token=lambda: 'synthetic', prepare=lambda *_: None, committed=receipt_failure, close=lambda: None
    )
    audio = SimpleNamespace(
        counts={}, preflight=lambda: None, measure=lambda row: measured.append(row.conversation_id) or (0, 20)
    )
    monkeypatch.setattr(
        cli, 'runtime', lambda: SimpleNamespace(codec=SimpleNamespace(decode_capture_segments=codec.decode))
    )
    monkeypatch.setattr(cli, 'Census', lambda *_: fake)
    monkeypatch.setattr(cli, 'Audio', lambda *_, **__: audio)
    monkeypatch.setattr(cli, 'Ledger', lambda *_, **__: ledger)
    monkeypatch.setattr(cli.firestore, 'Client', lambda **_: None)
    monkeypatch.setattr(cli.storage, 'Client', lambda **_: None)
    monkeypatch.setattr(cli.time, 'sleep', lambda _: None)
    monkeypatch.setenv('GCP_AGENT_TIER', 'synthetic-test')
    monkeypatch.setenv('CAPTURE_EMPTY_APPLY_AUTHORIZED', recovery.OPERATION)
    args = cli.parser().parse_args(
        [
            'hide',
            '--after',
            '2026-10-29T12:00:00Z',
            '--before',
            '2026-10-30T12:00:00Z',
            '--apply',
            '--concurrency',
            '1',
            '--max-count',
            '2',
            '--max-audio-seconds',
            '60',
            '--ledger',
            '/synthetic-ledger',
        ]
    )
    output = cli.run(args)
    assert output['stopped'] is True
    assert output['outcomes'] == {'hide_receipt_unproven': 1}
    assert measured == ['synthetic-capture']
    assert stores['synthetic-capture'].current.row['discarded'] is True
    assert stores['synthetic-second'].current.row['discarded'] is False


def test_cli_exits_nonzero_for_uncertain_mutation(monkeypatch):
    monkeypatch.setattr(cli.sys, 'argv', ['capture_empty_recovery.py', 'hide'])
    monkeypatch.setattr(cli, 'run', lambda _: {'stopped': True})
    assert cli.main() == 2
