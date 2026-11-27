"""Local stand-in for production's self-hosted language gate (Whisper-base behind Parakeet's /v2/language).

Runs in its own venv with ``mlx-whisper`` (never the backend's), as a one-shot batch: it reads a JSON list of
0600 WAV paths from a file, classifies each with Whisper-base on this Mac and writes ``[{"path", "language"}]``
to another file. ``language`` is Whisper's top-1 code, which is what ``batch_language.self_language_class``
reduces the production verdict to (``language_class(verdict.language)``).

    $OMI_PIPELINE_LAB_MLX_PYTHON -m testing.pipeline_lab.stt_routing.self_lid --in paths.json --out langs.json

Stdlib and mlx-whisper only: this module is never imported by the backend.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import wave

MODEL = 'mlx-community/whisper-base-mlx'
MODEL_ENV = 'OMI_PIPELINE_LAB_SELF_LID_MODEL'


def classify(paths: list[str], model: str) -> list[dict[str, str]]:
    import mlx_whisper
    import numpy as np

    out = []
    for path in paths:
        with wave.open(path, 'rb') as source:
            pcm = source.readframes(source.getnframes())
        audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=model, language=None, condition_on_previous_text=False, without_timestamps=True
        )
        out.append({'path': path, 'language': str(result.get('language') or 'und')})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--in', dest='source', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    paths = json.loads(open(args.source, encoding='utf-8').read())
    rows = classify(paths, os.environ.get(MODEL_ENV) or MODEL)
    os.umask(0o077)
    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump(rows, handle)
    return 0


if __name__ == '__main__':
    sys.exit(main())
