"""Held-out, hand-confirmed enrollment for a separate diagnostic only."""

import hashlib
import importlib
import json
from pathlib import Path
import wave

import numpy as np

from scripts.diarization_eval.local_artifacts import file_digest, private_json
from utils.stt.conversation_speakers import unit_voice_vector

EMBEDDING_REVISION = '837717ddb9ff5507820346191109dc79c958d614'


def declarations(recording):
    """Declare held-out identities before observing any predicted channels."""
    table = dict(recording['identity_table'])
    for span in recording['enrollment_spans']:
        label = span['truth']
        existing = recording['identity_table'].get(label)
        table[label] = existing or {'person_id': 'local-enrolled-' + hashlib.sha256(label.encode()).hexdigest()[:20]}
    return table


def embedding_from_pcm(samples):
    torch = importlib.import_module('torch')
    embedding = importlib.import_module('diarizer.embedding').embedding_inference_v2
    with torch.inference_mode():
        return embedding({'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': 16000})


def build_gallery(recording, wav, destination, *, extractor=None, base_gallery=None):
    table = declarations(recording)
    key = hashlib.sha256(
        json.dumps(
            {
                'audio': file_digest(wav),
                'spans': recording['enrollment_spans'],
                'identities': table,
                'embedding_revision': EMBEDDING_REVISION,
                'base_gallery': base_gallery or {},
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    destination = Path(destination)
    if destination.exists():
        cached = json.loads(destination.read_text())
        if cached['key'] == key:
            return cached
    extractor = extractor or embedding_from_pcm
    with wave.open(str(wav), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('enrollment_requires_canonical_pcm')
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
    gallery, names = dict(base_gallery or {}), {}
    for span in recording['enrollment_spans']:
        left, right = int(span['start'] * 16000), int(span['end'] * 16000)
        if not 0 <= left < right <= len(pcm) or not 6 <= span['end'] - span['start'] <= 10:
            raise ValueError('invalid_frozen_enrollment_span')
        identity = table[span['truth']]
        person = 'user' if identity.get('is_user') else identity['person_id']
        vector = unit_voice_vector(extractor(pcm[left:right]))
        if vector is None:
            raise ValueError('invalid_enrollment_embedding')
        gallery[person] = vector.tolist()
        names[person] = span['truth']
    result = {
        'key': key,
        'gallery': gallery,
        'identity_table': table,
        'names': names,
        'excluded_spans': [[s['start'], s['end']] for s in recording['enrollment_spans']],
        'embedding_revision': EMBEDDING_REVISION,
        'diagnostic_only': True,
    }
    private_json(destination, result)
    return result
