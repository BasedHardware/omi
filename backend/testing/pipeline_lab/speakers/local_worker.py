"""Production's diarizer models on this machine's CPU, for ``speakers`` peer recording (``--speakers record-local``).

Runs in the optional local-models venv (``requirements-local-speakers.txt``), never the backend venv, and is
started by :mod:`testing.pipeline_lab.speakers.peer` as a worker process. It answers exactly what the hosted
diarizer answers, through the diarizer's own code:

- ``diarization``: ``diarizer/final_pass.py`` ``decode_audio`` + ``infer`` (pyannote community-1 at the
  pinned revision, exclusive turns, overlaps, and v2 WeSpeaker centroids);
- ``embedding``: ``diarizer/embedding.py`` ``_validate_audio_duration`` + ``embedding_inference_v2`` on the
  uploaded WAV (``/v2/embedding``).

CPU FP32 is not CUDA parity: cassettes it writes are filed with ``source: local`` and a ``cpu`` device.

Protocol: one JSON request per stdin line ``{"op": "diarization"|"embedding", "path": FILE,
"content_type": ..., "min_speakers": N, "max_speakers": N}``; one JSON line back ``{"ok": true, "body": ...}``
or ``{"ok": false, "status": HTTP status, "detail": ...}``. Input files are owner-only files under the lab
root that the peer writes and deletes.

The diarizer modules import each other as top-level modules (``from embedding import ...``), so the worker
puts ``backend/diarizer`` and ``backend`` on ``sys.path`` the way the diarizer image does.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[3]
DIARIZER = BACKEND / 'diarizer'


def _modules() -> tuple[Any, Any]:
    for path in (str(BACKEND), str(DIARIZER)):
        if path not in sys.path:
            sys.path.insert(0, path)
    cwd = os.getcwd()
    # embedding.py creates ./_temp at import: keep it inside the private work directory.
    os.chdir(os.environ.get('OMI_PIPELINE_LAB_SPEAKERS_WORKDIR') or cwd)
    try:
        import embedding  # type: ignore[import-not-found]
        import final_pass  # type: ignore[import-not-found]
    finally:
        os.chdir(cwd)
    return final_pass, embedding


# An independent reference for silver truth (``silver.py``), never a production path: NVIDIA Streaming Sortformer
# v2 (CC BY 4.0), pinned. Up to four speakers; streaming settings from its model card (high-latency offline use).
REFERENCE_MODEL = ('nvidia/diar_streaming_sortformer_4spk-v2', '84edd514b8ef', 'diar_streaming_sortformer_4spk-v2.nemo')
_REFERENCE: list = []


def reference_diarization(path: str) -> dict:
    if not _REFERENCE:
        from huggingface_hub import hf_hub_download
        from nemo.collections.asr.models import SortformerEncLabelModel

        repo, revision, filename = REFERENCE_MODEL
        model = SortformerEncLabelModel.restore_from(
            hf_hub_download(repo, filename, revision=revision), map_location='cpu'
        )
        model.eval()
        modules = model.sortformer_modules
        modules.chunk_len, modules.chunk_right_context, modules.fifo_len = 340, 40, 40
        modules.spkcache_update_period, modules.spkcache_len = 300, 188
        _REFERENCE.append(model)
    rows = _REFERENCE[0].diarize(audio=[path], batch_size=1)[0]
    turns = []
    for row in rows:
        start, end, speaker = str(row).split()
        turns.append({'start': float(start), 'end': float(end), 'speaker': speaker})
    return {'turns': turns, 'model': '/'.join(REFERENCE_MODEL[:2])}


def handle(request: dict, final_pass: Any, embedding: Any) -> dict:
    from fastapi import HTTPException

    try:
        if request['op'] == 'diarization':
            body = Path(request['path']).read_bytes()
            waveform = final_pass.decode_audio(body, request.get('content_type') or 'audio/pcm')
            result = final_pass.infer(waveform, request.get('min_speakers'), request.get('max_speakers'))
            result['provenance'] = {**result.get('provenance', {}), 'device': 'cpu', 'dtype': 'float32'}
            return {'ok': True, 'body': result}
        if request['op'] == 'embedding':
            path = request['path']
            embedding._validate_audio_duration(path)
            vector = embedding.embedding_inference_v2(embedding._load_audio_for_inference(path))
            return {'ok': True, 'body': vector.tolist()}
        if request['op'] == 'reference_diarization':
            return {'ok': True, 'body': reference_diarization(request['path'])}
        return {'ok': False, 'status': 404, 'detail': 'unknown op'}
    except HTTPException as error:
        return {'ok': False, 'status': error.status_code, 'detail': error.detail}


def main() -> int:
    # Only protocol lines reach the peer: models and libraries print to stdout (pyannote's clustering
    # warnings), so stdout is the error stream for everything else.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    final_pass, embedding = _modules()
    protocol.write(json.dumps({'ready': True, 'revision': final_pass.MODEL_REVISION}) + '\n')
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line), final_pass, embedding)
        except Exception as error:  # the peer turns this into an HTTP 500 for the product client
            reply = {'ok': False, 'status': 500, 'detail': f'{type(error).__name__}: {error}'[:500]}
        protocol.write(json.dumps(reply) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
