"""Held-out enrollment stays independent of inferred channels and cached text."""

import json
import wave

import numpy as np

from scripts.diarization_eval.enrollment import build_gallery, declarations


def test_reserved_enrollment_keeps_predeclared_ids_and_excludes_exact_spans(tmp_path):
    wav = tmp_path / 'synthetic.wav'
    with wave.open(str(wav), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 320000)
    recording = {
        'identity_table': {'owner': {'is_user': True}},
        'enrollment_spans': [
            {'truth': 'owner', 'start': 0, 'end': 6},
            {'truth': 'stranger', 'start': 10, 'end': 16},
        ],
    }
    calls = []

    def extractor(samples):
        calls.append(len(samples))
        return np.ones(256)

    destination = tmp_path / 'enrollment.json'
    rich = build_gallery(recording, wav, destination, extractor=extractor)
    assert rich['identity_table'] == declarations(recording)
    assert rich['identity_table']['owner'] == {'is_user': True}
    assert len(rich['gallery']) == 2
    assert rich['excluded_spans'] == [[0, 6], [10, 16]]
    assert calls == [96000, 96000]
    assert json.loads(destination.read_text())['diagnostic_only'] is True
    assert destination.stat().st_mode & 0o777 == 0o600
    assert build_gallery(recording, wav, destination, extractor=extractor) == rich
    assert len(calls) == 2
