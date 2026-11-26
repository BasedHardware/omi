"""Run one speaker arm over prepared conversations, in a fresh process, through product code only.

The bench (:mod:`testing.pipeline_lab.speakers.bench`) writes a job file and starts this module once per arm with
the arm's environment, because product speaker policy reads its operating points from the environment at import
(``utils/speakers/policy.py``). An arm may run another backend tree: the bench sets that tree as the working
directory and ``PYTHONPATH`` and starts this file by path, so only product modules come from the arm's tree.

Engines:

- ``final_pass``: ``utils.conversations.final_pass_pyannote.run_final_pass`` (the whole-conversation pass the
  batch lane runs) with the production ``HttpDiarizer`` against ``HOSTED_DIARIZATION_API_URL`` (the lab's
  speaker peer), the conversation's words and the gallery as the voiceprint cache.

Input job (JSON): ``{"engine", "conversations": [{"key", "pcm_path", "words": [{start, end, text}],
"owner_reserved"}], "gallery": {identity: vector}, "out": PATH}``. Output: one JSON line per conversation with the
segments the engine produced (clocks on the audio, identity fields) and the engine's outcome summary.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def _segment(segment) -> dict:
    data = segment.model_dump() if hasattr(segment, 'model_dump') else dict(segment)
    return {
        'start': float(data['start']),
        'end': float(data['end']),
        'text': data.get('text') or '',
        'speaker': data.get('speaker'),
        'speaker_id': data.get('speaker_id'),
        'speaker_id_scope': data.get('speaker_id_scope'),
        'is_user': bool(data.get('is_user')),
        'person_id': data.get('person_id'),
    }


def final_pass(conversation: dict, gallery: dict) -> dict:
    from utils.conversations.final_pass_pyannote import run_final_pass

    pcm = Path(conversation['pcm_path']).read_bytes()
    words = [{'timestamp': [w['start'], w['end']], 'text': w['text']} for w in conversation['words']]
    cache = {identity: {'embedding': vector} for identity, vector in gallery.items()}
    started = time.monotonic()
    segments, outcome = run_final_pass(
        pcm,
        words,
        None,
        cache,
        deadline=time.monotonic() + 3600,
        conversation_id=conversation['key'],
        owner_reserved=bool(conversation.get('owner_reserved')),
        lane='lab',
        include_assignments=False,
        record_outcome=False,
    )
    return {
        'key': conversation['key'],
        'segments': [_segment(s) for s in segments or []],
        'outcome': {k: v for k, v in outcome.items() if k not in ('assignments', 'centroids')},
        'seconds': round(time.monotonic() - started, 3),
    }


ENGINES = {'final_pass': final_pass}


def main(argv: list[str]) -> int:
    job = json.loads(Path(argv[0]).read_text())
    engine = ENGINES[job['engine']]
    with open(job['out'], 'w') as out:
        for conversation in job['conversations']:
            try:
                result = engine(conversation, job.get('gallery') or {})
            except Exception as error:  # one conversation's failure is a result, not the end of the arm
                result = {'key': conversation['key'], 'error': f'{type(error).__name__}: {error}'[:300]}
            out.write(json.dumps(result) + '\n')
            out.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
