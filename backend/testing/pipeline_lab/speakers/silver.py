"""Silver truth for corpora without hand labels: two independent diarizers must agree, identity must be certain.

    python -m testing.pipeline_lab.speakers silver --corpus owner-60d [--speakers record-local]

Per conversation (words must exist, see ``bench --words record-local``):

1. **Who spoke with whom.** Production's diarizer (pyannote community-1, through the speaker peer, the same
   cassette the ``final_pass`` arm plays) and an independent reference (NVIDIA Streaming Sortformer v2, run by
   ``local_worker`` and cached privately) each label every word. Reference voices are mapped onto community-1
   voices by Hungarian matching on shared words. A word whose two labels agree keeps the community-1 voice; any
   disagreement, or a word either model leaves in a gap, is ``unsure`` and excluded from scoring.
2. **Who each voice is.** A voice is the owner or an enrolled person only when its community-1 centroid is
   within ``STRICT`` (0.45) cosine distance of that voiceprint with a 0.10 margin, and for the owner, when it is
   also the near-field voice (within 3 dB of the loudest voice: the pendant hears its wearer loudest). A voice
   farther than ``STRANGER`` (0.70) from every voiceprint is nobody enrolled. Everything else is ``?``: its words
   still count for attribution but not for identity metrics. A production manual assignment (the owner's own
   correction) overrides both, for the voice that holds most of the corrected segment's words.

Limits, stated in every truth file: attribution scored against silver favours community-1 (it is one of the two
voters), so silver ranks naming, assignment and grouping changes downstream of the diarizer, and production's
labels, but cannot prove the diarizer itself; identity shares the gallery and embedding model with the arms, so
silver cannot tune the naming threshold near 0.45-0.70. Gold labels (a person listening) settle both.
A ``truth.json`` of kind ``gold`` is never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from array import array
from pathlib import Path
from typing import Any, Optional

from testing.pipeline_lab.speakers import corpus as corpus_mod

STRICT = 0.45
MARGIN = 0.10
STRANGER = 0.70
NEAR_FIELD_DB = 3.0
UNSURE = 'unsure'
UNKNOWN = '?'


def word_labels(words: list[dict], turns: list[dict]) -> list[Optional[str]]:
    from utils.conversations.final_pass_assignment import assign_words
    from utils.stt.diarization_turns import exclusive_from_activity

    clean = [t for t in turns if t['end'] > t['start']]
    if not clean:
        return [None] * len(words)
    rows = [{'timestamp': [w['start'], w['end']], 'text': ''} for w in words]
    return [w['speaker'] for w in assign_words(rows, exclusive_from_activity(clean))]


def map_reference(primary: list[Optional[str]], reference: list[Optional[str]]) -> dict[str, str]:
    from collections import Counter

    import numpy as np
    from scipy.optimize import linear_sum_assignment

    pairs = Counter((r, p) for p, r in zip(primary, reference) if p is not None and r is not None)
    refs = sorted({r for r, _ in pairs})
    prims = sorted({p for _, p in pairs})
    if not refs or not prims:
        return {}
    matrix = np.array([[pairs[r, p] for p in prims] for r in refs])
    rows, cols = linear_sum_assignment(-matrix)
    return {refs[r]: prims[c] for r, c in zip(rows, cols) if matrix[r, c] > 0}


def consensus(primary: list[Optional[str]], reference: list[Optional[str]]) -> list[str]:
    mapping = map_reference(primary, reference)
    return [
        p if p is not None and r is not None and mapping.get(r) == p else UNSURE for p, r in zip(primary, reference)
    ]


def word_levels(pcm: bytes, words: list[dict]) -> list[Optional[float]]:
    samples = array('h')
    samples.frombytes(pcm)
    levels = []
    for w in words:
        left, right = int(w['start'] * 16000), int(w['end'] * 16000)
        chunk = samples[left:right]
        if len(chunk) < 160:
            levels.append(None)
            continue
        rms = math.sqrt(sum(v * v for v in chunk) / len(chunk))
        levels.append(20 * math.log10(max(rms, 1.0) / 32768))
    return levels


def identities(
    labels: list[str], levels: list[Optional[float]], centroids: dict, gallery: dict
) -> tuple[dict[str, Optional[str]], dict[str, Any]]:
    from statistics import median

    from utils.stt.conversation_speakers import unit_voice_vector, voice_cosine_distance

    prints = {k: unit_voice_vector(v) for k, v in gallery.items()}
    prints = {k: v for k, v in prints.items() if v is not None}
    loudness = {}
    for label in {l for l in labels if l != UNSURE}:
        values = [v for l, v in zip(labels, levels) if l == label and v is not None]
        if len(values) >= 10:
            loudness[label] = median(values)
    loudest = max(loudness.values()) if loudness else None
    result: dict[str, Optional[str]] = {}
    evidence = {}
    for label in sorted({l for l in labels if l != UNSURE}):
        vector = unit_voice_vector((centroids.get(label) or {}).get('embedding'))
        if vector is None or not prints:
            result[label] = UNKNOWN
            continue
        ranked = sorted((voice_cosine_distance(vector, v), k) for k, v in prints.items() if v.shape == vector.shape)
        if not ranked:
            result[label] = UNKNOWN
            continue
        best, who = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else math.inf
        near = label in loudness and loudest is not None and loudest - loudness[label] <= NEAR_FIELD_DB
        if best <= STRICT and second - best >= MARGIN and (who != 'user' or near):
            result[label] = who
        elif best >= STRANGER:
            result[label] = None
        else:
            result[label] = UNKNOWN
        evidence[label] = {'best_distance': round(best, 3), 'near_field': near}
    return result, evidence


def manual_overrides(conversation: corpus_mod.Conversation, words: list[dict], labels: list[str]) -> dict[str, str]:
    from collections import Counter

    stored = conversation.production or {}
    offset = stored.get('segment_clock_offset')
    if offset is None:
        return {}
    out = {}
    for segment in stored.get('segments') or []:
        if segment.get('speaker_label_source') != 'manual' or segment.get('start') is None:
            continue
        identity = 'user' if segment.get('is_user') else segment.get('person_id')
        if not identity:
            continue
        left, right = segment['start'] - offset, segment['end'] - offset
        votes = Counter(l for w, l in zip(words, labels) if l != UNSURE and w['start'] < right and w['end'] > left)
        if votes:
            out[votes.most_common(1)[0][0]] = identity
    return out


def to_turns(words: list[dict], labels: list[str]) -> list[dict]:
    turns: list[dict] = []
    for w, label in zip(words, labels):
        if turns and turns[-1]['speaker'] == label and w['start'] - turns[-1]['end'] < 1.0:
            turns[-1]['end'] = max(turns[-1]['end'], w['end'])
        else:
            turns.append({'start': w['start'], 'end': max(w['end'], w['start'] + 0.01), 'speaker': label})
    # exclusive: a word clock can start before the previous word ends
    for a, b in zip(turns, turns[1:]):
        if b['start'] < a['end']:
            b['start'] = a['end'] = (a['end'] + b['start']) / 2
    return [t for t in turns if t['end'] > t['start']]


def reference_turns(conversation: corpus_mod.Conversation, local: Any) -> dict:
    from testing.pipeline_lab.scenario.paths import private_lab_root
    from testing.pipeline_lab.store import atomic_write_json, ensure_private_dir

    digest = hashlib.sha256(conversation.audio_path.read_bytes()).hexdigest()
    cache = ensure_private_dir(ensure_private_dir(private_lab_root() / 'speakers') / 'reference_cache')
    path = cache / f'{digest}.json'
    if path.is_file():
        return json.loads(path.read_text())
    reply = local.run({'op': 'reference_diarization', 'path': str(conversation.audio_path)})
    if not reply.get('ok'):
        raise RuntimeError(f"reference diarization failed: {reply.get('detail')}")
    atomic_write_json(path, reply['body'])
    return reply['body']


def silver_for(conversation: corpus_mod.Conversation, peer: Any, gallery: dict) -> Optional[dict]:
    words = (conversation.words or {}).get('words')
    if not words:
        return None
    pcm = conversation.pcm()
    status, primary = peer.answer('/v2/diarization', {}, pcm, 'audio/pcm')
    if status != 200:
        raise RuntimeError(f'{conversation.key}: community-1 unavailable ({status})')
    reference = reference_turns(conversation, peer.local)
    labels = consensus(word_labels(words, primary['turns']), word_labels(words, reference['turns']))
    ids, evidence = identities(labels, word_levels(pcm, words), primary.get('centroids') or {}, gallery)
    overrides = manual_overrides(conversation, words, labels)
    ids.update(overrides)
    ids[UNSURE] = None
    unsure = sum(l == UNSURE for l in labels)
    return {
        'kind': 'silver',
        'method': {
            'voices': 'consensus of pyannote community-1 (production pin) and Streaming Sortformer v2',
            'identity': f'voiceprint <= {STRICT} with margin {MARGIN}, owner also near-field; manual overrides',
            'reference_model': reference.get('model'),
            'limits': 'favours community-1 on attribution; shares gallery and embedding model on identity',
        },
        'turns': to_turns(words, labels),
        'identities': ids,
        'stats': {
            'words': len(words),
            'unsure_words': unsure,
            'voices': len({l for l in labels if l != UNSURE}),
            'owner_voice': any(v == 'user' for v in ids.values()),
            'unknown_identity_voices': sum(v == UNKNOWN for v in ids.values()),
            'manual_overrides': len(overrides),
        },
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.speakers silver', description=__doc__)
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--speakers', choices=('replay', 'record-local'), default='replay')
    parser.add_argument('--key', action='append', default=[])
    args = parser.parse_args(argv)
    from testing.pipeline_lab.speakers.bench import gallery_for
    from testing.pipeline_lab.speakers.peer import LocalModels, SpeakerPeer

    corpus = corpus_mod.load(args.corpus)
    if corpus.public:
        print('error: public corpora carry exact truth', file=sys.stderr)
        return 2
    import os

    totals = {'conversations': 0, 'words': 0, 'unsure_words': 0, 'owner_voice': 0, 'skipped_gold': 0}
    with SpeakerPeer(args.speakers) as peer:
        if peer.local is None:
            peer.local = LocalModels(peer.workdir)
        os.environ.update(peer.env())
        gallery = gallery_for(corpus)
        for conversation in corpus.conversations(args.key or None):
            if (conversation.truth or {}).get('kind') == 'gold':
                totals['skipped_gold'] += 1
                continue
            truth = silver_for(conversation, peer, gallery)
            if truth is None:
                continue
            corpus_mod.write_json(conversation.path / 'truth.json', truth, private=True)
            totals['conversations'] += 1
            totals['words'] += truth['stats']['words']
            totals['unsure_words'] += truth['stats']['unsure_words']
            totals['owner_voice'] += truth['stats']['owner_voice']
            print(json.dumps({'key': conversation.key[:6], **truth['stats']}))
    print(json.dumps(totals))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
