"""Fixed-denominator split qualification without model inference."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import wave

import pytest

from scripts.diarization_eval.split_quality import _digest, main, private_output_dir, qualify, verify_provenance


def units(boundary=None):
    if boundary is None:
        return [{'offset': 0, 'payload': {'audio_seconds': 10}}]
    return [
        {'offset': 0, 'payload': {'audio_seconds': boundary}},
        {'offset': boundary, 'payload': {'audio_seconds': 10 - boundary}},
    ]


def manifest():
    return {
        'crop_seconds': 10,
        'unsplit': units(),
        'cases': [units(4), units(6)],
        'reference_words': [{'start': 3, 'end': 5, 'speaker': 'voice'}, {'start': 5, 'end': 7, 'speaker': 'voice'}],
        'identity_table': {'voice': {'is_user': True}},
        'excluded_spans': [],
    }


def score(truth, turns, identities, **kwargs):
    return {
        'words': len(truth),
        'owner_enrolled_words': len(truth),
        'owner_enrolled_accuracy': turns,
        'engineering_gate': 'PASS' if turns >= 0.9 else 'FAIL',
    }


def test_split_gate_uses_identical_frozen_words_and_per_case_loss():
    frozen = manifest()
    calls = []

    def scorer(truth, *args, **kwargs):
        calls.append(deepcopy(truth))
        return score(truth, *args, **kwargs)

    result = qualify(
        frozen, project=lambda value: 0.93 if len(value) == 1 else 0.92, scorer=scorer, provenance_verified=True
    )
    assert result['split_gate'] == 'PASS'
    assert calls == [frozen['reference_words']] * 3
    assert all(case['mid_speech_boundary'] for case in result['splits'])
    result = qualify(
        frozen, project=lambda value: 0.95 if len(value) == 1 else 0.92, scorer=score, provenance_verified=True
    )
    assert result['split_gate'] == 'FAIL'


@pytest.mark.parametrize('change', ['missing', 'overlap', 'repeat', 'no-mid-speech'])
def test_incomplete_or_unproven_splits_cannot_pass(change):
    data = manifest()
    if change == 'missing':
        data['cases'][0][1]['offset'] += 1
    elif change == 'overlap':
        data['cases'][0][1]['offset'] -= 1
    elif change == 'repeat':
        data['cases'][1] = data['cases'][0]
    else:
        data['reference_words'] = [{'start': 0, 'end': 1, 'speaker': 'voice'}]
    with pytest.raises(ValueError):
        qualify(data, project=lambda value: 0.95, scorer=score, provenance_verified=True)


def test_changed_denominator_and_missing_identity_evidence_fail():
    data = manifest()
    counter = 0

    def scorer(truth, turns, identities, **kwargs):
        nonlocal counter
        counter += 1
        result = score(truth, turns, identities)
        if counter > 1:
            result['owner_enrolled_words'] -= 1
        return result

    assert qualify(data, project=lambda value: 0.95, scorer=scorer, provenance_verified=True)['split_gate'] == 'FAIL'
    result = qualify(
        data,
        project=lambda value: None,
        scorer=lambda *a, **k: {'words': 2, 'owner_enrolled_words': 0, 'owner_enrolled_accuracy': None},
        provenance_verified=True,
    )
    assert result['split_gate'] == 'FAIL'


def test_unverified_provenance_is_blocked_before_projection():
    assert qualify(manifest(), project=lambda value: pytest.fail('must not project'))['split_gate'] == 'BLOCKED'


def receipt_manifest(tmp_path):

    frames = b''.join((index % 32767).to_bytes(2, 'little') for index in range(160000))

    def wav(path, content):
        with wave.open(str(path), 'wb') as handle:
            handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            handle.writeframes(content)

    source = tmp_path / 'whole.wav'
    wav(source, frames)
    data = manifest()
    data.update(
        source_audio=str(source),
        crop_audio=str(source),
        source_sha256=_digest(source),
        crop_pcm_sha256=hashlib.sha256(frames).hexdigest(),
        crop_start_seconds=0,
        inference_config={'asr_model_revision': 'synthetic-pinned', 'dtype': 'float32'},
    )
    config_hash = hashlib.sha256(
        json.dumps(data['inference_config'], sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    for case, selected in enumerate([data['unsplit'], *data['cases']]):
        for index, unit in enumerate(selected):
            duration = unit['payload']['audio_seconds']
            content = frames[int(unit['offset'] * 32000) : int((unit['offset'] + duration) * 32000)]
            stem = tmp_path / f'{case}-{index}'
            audio, payload, receipt = stem.with_suffix('.wav'), stem.with_suffix('.json'), stem.with_suffix('.receipt')
            wav(audio, content)
            payload.write_text(json.dumps(unit['payload']))
            receipt.write_text(
                json.dumps(
                    {
                        'source_sha256': data['source_sha256'],
                        'crop_pcm_sha256': data['crop_pcm_sha256'],
                        'crop_start_seconds': 0,
                        'offset': unit['offset'],
                        'duration_seconds': duration,
                        'input_pcm_sha256': hashlib.sha256(content).hexdigest(),
                        'payload_sha256': _digest(payload),
                        'inference_config_sha256': config_hash,
                    }
                )
            )
            unit.update(audio=str(audio), payload=str(payload), receipt=str(receipt))
    return data


def test_provenance_verifies_actual_pcm_payload_and_common_config(tmp_path):

    data = receipt_manifest(tmp_path)
    loaded = verify_provenance(data)
    assert loaded['unsplit'][0]['payload']['audio_seconds'] == 10


@pytest.mark.parametrize('tamper', ['payload', 'settings', 'input', 'offset', 'missing-receipt'])
def test_stale_or_unrelated_same_duration_payloads_are_rejected(tmp_path, tamper):

    data = receipt_manifest(tmp_path)
    unit = data['cases'][0][0]
    if tamper == 'payload':
        Path(unit['payload']).write_text('{"audio_seconds":4,"words":[]}')
    elif tamper == 'settings':
        data['inference_config']['dtype'] = 'other'
    elif tamper == 'input':
        audio = Path(unit['audio'])
        value = bytearray(audio.read_bytes())
        value[-1] ^= 1
        audio.write_bytes(value)
    elif tamper == 'offset':
        unit['offset'] += 0.5
    else:
        Path(unit['receipt']).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_provenance(data)


@pytest.mark.parametrize('linked', [False, True])
def test_private_split_output_rejects_checkout_and_worktree_before_writing(tmp_path, linked):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    marker = checkout / '.git'
    if linked:
        marker.write_text('gitdir: synthetic-shared-git')
    else:
        marker.mkdir()
    output = checkout / 'split-results'
    with pytest.raises(ValueError, match='outside a Git checkout'):
        private_output_dir(output)
    assert not output.exists()


def test_private_split_output_resolves_symlink_into_checkout(tmp_path):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    (checkout / '.git').mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(checkout, target_is_directory=True)
    with pytest.raises(ValueError, match='outside a Git checkout'):
        private_output_dir(alias / 'split-results')
    assert not (checkout / 'split-results').exists()


def test_private_split_output_outside_checkout_has_owner_only_permissions(tmp_path):
    output = private_output_dir(tmp_path / 'private-results')
    assert output.stat().st_mode & 0o777 == 0o700


def test_cli_rejects_checkout_before_manifest_or_log_write(tmp_path, monkeypatch, capsys):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    (checkout / '.git').mkdir()
    output = checkout / 'split-results'
    monkeypatch.setattr(
        'sys.argv', ['split_quality', '--manifest', str(tmp_path / 'private-input.json'), '--output', str(output)]
    )
    assert main() == 2
    assert json.loads(capsys.readouterr().out) == {'split_gate': 'BLOCKED', 'reason': 'private_output_required'}
    assert not output.exists()
