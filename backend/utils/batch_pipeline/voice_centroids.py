"""Bounded Omi-v2 evidence; no names, transcript, audio or IO in its schema."""

import io
import base64
import json
import math
import re
import wave
import time

import numpy as np

SCHEMA = 1
SPACE = 'wespeaker-resnet34:v2'
DIMENSION = 256
MAX_LABELS = 32
MAX_BYTES = 64 * 1024
CAPTURE_TTL = 24 * 3600
FINALIZED_TTL = 3600
MAX_CLIP_SECONDS = 15
RATE = 16000


def deadline(capture_at: float, finalized_at: float | None = None) -> float:
    hard = capture_at + CAPTURE_TTL
    return min(hard, finalized_at + FINALIZED_TTL) if finalized_at is not None else hard


def encode(payload: dict) -> bytes:
    packed = {
        **payload,
        'labels': [
            {**row, 'vector': base64.b64encode(np.asarray(row['vector'], dtype='<f4').tobytes()).decode('ascii')}
            for row in payload['labels']
        ],
    }
    body = json.dumps(packed, allow_nan=False, separators=(',', ':')).encode()
    if len(body) > MAX_BYTES:
        raise ValueError('voice evidence byte budget')
    decode(body)
    return body


def decode(body: bytes) -> dict:
    if len(body) > MAX_BYTES:
        raise ValueError('voice evidence byte budget')
    payload = json.loads(body)
    if set(payload) != {'schema', 'space', 'capture_at', 'expires_at', 'labels'}:
        raise ValueError('closed voice evidence schema required')
    if payload['schema'] != SCHEMA or payload['space'] != SPACE:
        raise ValueError('incompatible voice evidence')
    capture, expires = payload['capture_at'], payload['expires_at']
    if any(type(v) not in {int, float} or not math.isfinite(v) for v in (capture, expires)):
        raise ValueError('finite capture clocks required')
    if not 0 <= capture < expires <= deadline(capture):
        raise ValueError('invalid voice evidence expiry')
    labels = payload['labels']
    if not isinstance(labels, list) or len(labels) > MAX_LABELS:
        raise ValueError('voice evidence label budget')
    seen = set()
    for row in labels:
        if set(row) != {'label', 'vector', 'seconds'}:
            raise ValueError('closed centroid schema required')
        label, seconds = row['label'], row['seconds']
        if not isinstance(label, str) or not re.fullmatch(r'SPEAKER_[0-9]{2,3}', label) or label in seen:
            raise ValueError('invalid original voice label')
        seen.add(label)
        if not isinstance(row['vector'], str):
            raise ValueError('float32 vector envelope required')
        vector = np.frombuffer(base64.b64decode(row['vector'], validate=True), dtype='<f4')
        if vector.shape != (DIMENSION,) or not np.isfinite(vector).all():
            raise ValueError('incompatible Omi-v2 dimension')
        if abs(float(np.linalg.norm(vector)) - 1) > 1e-4:
            raise ValueError('normalized centroid required')
        if type(seconds) not in {int, float} or not math.isfinite(seconds) or not 0.5 <= seconds <= MAX_CLIP_SECONDS:
            raise ValueError('invalid unique speech evidence')
        row['vector'] = vector.tolist()
    return payload


def extract(wav: bytes, turns: list, capture_at: float, extractor, *, execution_deadline: float = float('inf')) -> dict:
    """One <=15s clip per local label, exclusively attributed PCM only.

    Merge each label's intervals before subtracting every other label. This
    prevents overlapping/duplicate turns from multiplying measured evidence.
    """
    with wave.open(io.BytesIO(wav), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, RATE):
            raise ValueError('canonical PCM required')
        frames = source.getnframes()
        pcm = source.readframes(frames)
    by_label = {}
    for turn in turns:
        if time.monotonic() >= execution_deadline:
            raise TimeoutError('voice extraction budget')
        label, start, end = turn['speaker'], float(turn['start']), float(turn['end'])
        if not isinstance(label, str) or not re.fullmatch(r'SPEAKER_[0-9]{2,3}', label):
            raise ValueError('invalid original voice label')
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= frames / RATE + 0.001:
            raise ValueError('invalid diarization clocks')
        by_label.setdefault(label, []).append((round(start * RATE), min(frames, round(end * RATE))))
    if len(by_label) > MAX_LABELS:
        raise ValueError('voice evidence label budget')
    merged = {}
    for label, spans in by_label.items():
        union = []
        for start, end in sorted(spans):
            if union and start <= union[-1][1]:
                union[-1] = (union[-1][0], max(union[-1][1], end))
            else:
                union.append((start, end))
        merged[label] = union
    rows = []
    for label, spans in merged.items():
        for other, overlaps in merged.items():
            if label != other:
                for low, high in overlaps:
                    if time.monotonic() >= execution_deadline:
                        raise TimeoutError('voice extraction budget')
                    spans = [p for a, b in spans for p in ((a, min(b, low)), (max(a, high), b)) if p[1] > p[0]]
        clip = bytearray()
        for start, end in spans:
            remaining = MAX_CLIP_SECONDS * RATE * 2 - len(clip)
            clip.extend(pcm[start * 2 : min(end * 2, start * 2 + remaining)])
            if len(clip) >= MAX_CLIP_SECONDS * RATE * 2:
                break
        if len(clip) < RATE:  # 0.5s minimum; the name matcher has its own higher floor.
            continue
        output = io.BytesIO()
        with wave.open(output, 'wb') as target:
            target.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            target.writeframes(clip)
        vector = np.asarray(extractor(output.getvalue()), dtype=np.float32).reshape(-1)
        if vector.shape != (DIMENSION,) or not np.isfinite(vector).all() or np.linalg.norm(vector) <= 0:
            raise ValueError('incompatible Omi-v2 embedding')
        vector /= np.linalg.norm(vector)
        rows.append({'label': label, 'vector': vector.tolist(), 'seconds': len(clip) / (RATE * 2)})
    payload = {
        'schema': SCHEMA,
        'space': SPACE,
        'capture_at': capture_at,
        'expires_at': deadline(capture_at),
        'labels': rows,
    }
    encode(payload)
    return payload
