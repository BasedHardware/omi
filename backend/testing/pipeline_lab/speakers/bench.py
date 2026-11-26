"""Speaker bench: run speaker-labeling arms over a corpus and score them. The loop for speaker experiments.

    cd backend
    python -m testing.pipeline_lab.speakers bench --corpus public-libri                    # replay, CI-safe
    python -m testing.pipeline_lab.speakers bench --corpus owner-60d --speakers record-local \\
        --arm base --arm 'tight:CONVERSATION_SPEAKER_VOICE_MATCH_THRESHOLD=0.45' --arm 'head@/path/to/backend'

An **arm** is one way of labeling speakers: an engine, an environment overlay (product operating points read
their environment at import, so each arm is a fresh process) and optionally another backend tree. Spec:
``NAME[@BACKEND_DIR][:ENGINE][:KEY=VALUE,KEY=VALUE]``. Engines (``arm_runner.ENGINES``): ``final_pass`` (default).
The built-in arm ``production`` is what production stored (owner corpora), placed on the audio clock.

Every arm's model calls go to the lab's speaker peer (:mod:`peer`): ``replay`` answers from cassettes only (a miss
fails that conversation), ``record-local`` runs production's diarizer code on this CPU for misses. Words come from
the corpus (``words.json``); ``--words record-local`` transcribes missing ones with local Parakeet first.

Output: ``report.json`` (per arm: pooled scorecard, per-conversation scorecards keyed by corpus key, agreement with
``production``, peer calls) and ``summary.md`` in ``--out`` (default: a fresh owner-only directory under the lab
root). Numbers only. Exit 0, or 1 when a ``--gate`` fails, 2 on an error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from testing.pipeline_lab.speakers import corpus as corpus_mod
from testing.pipeline_lab.speakers import score
from testing.pipeline_lab.speakers.peer import CassetteStore, SpeakerPeer

BACKEND = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).with_name('arm_runner.py')
# The arm process sees only these from the caller; never cloud credentials.
PASS_ENV = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'DYLD_FALLBACK_LIBRARY_PATH')
ISOLATION_ENV = {
    'GOOGLE_CLOUD_PROJECT': 'demo-lab-speakers',
    'OMI_ENV_STAGE': 'offline',
    'PYTHONDONTWRITEBYTECODE': '1',
}
METRICS = (
    'attribution',
    'owner_precision',
    'owner_recall',
    'named_accuracy',
    'wrong_name_rate',
    'named_coverage',
    'mean_abs_speaker_count_error',
)


@dataclass
class Arm:
    name: str
    engine: str = 'final_pass'
    env: dict = field(default_factory=dict)
    backend: Optional[Path] = None

    @classmethod
    def parse(cls, spec: str) -> 'Arm':
        head, *rest = spec.split(':', 2)
        name, _, backend = head.partition('@')
        engine, env = 'final_pass', {}
        for part in rest:
            if '=' in part:
                env.update(dict(item.split('=', 1) for item in part.split(',') if item))
            elif part:
                engine = part
        if not name or name == 'production':
            raise ValueError('an arm needs a name other than "production"')
        return cls(name=name, engine=engine, env=env, backend=Path(backend).resolve() if backend else None)

    def describe(self) -> dict:
        return {'engine': self.engine, 'env': self.env, 'backend': str(self.backend) if self.backend else None}


def ensure_words(conversation: corpus_mod.Conversation, *, record: bool, private: bool) -> list[dict]:
    if conversation.words is not None:
        return conversation.words['words']
    if not record:
        raise FileNotFoundError(f'{conversation.key}: no words.json; run with --words record-local')
    from testing.pipeline_lab.cassette import local_parakeet

    python = os.environ.get(local_parakeet.PYTHON_ENV) or os.environ.get('OMI_PIPELINE_LAB_LOCAL_SPEAKERS_PYTHON')
    if not python:
        raise RuntimeError(local_parakeet.INSTALL)
    revision = local_parakeet.asr_revision()
    pcm = conversation.pcm()
    words = local_parakeet.Worker(python, revision)(pcm, None, spans=local_parakeet.speech_windows(pcm))
    value = {
        'source': 'local',
        'model': local_parakeet.model_key(revision),
        'windows': 'vad',
        'words': [{'start': round(w.start, 3), 'end': round(w.end, 3), 'text': w.text} for w in words],
    }
    corpus_mod.write_json(conversation.path / 'words.json', value, private=private)
    conversation.words = value
    return value['words']


def words_main(argv: Optional[list[str]] = None) -> int:
    """``python -m testing.pipeline_lab.speakers words --corpus NAME [--jobs N]``: record missing words locally."""
    from concurrent.futures import ThreadPoolExecutor

    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.speakers words')
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--jobs', type=int, default=2, help='parallel Parakeet workers (about 3 GB each)')
    parser.add_argument('--key', action='append', default=[])
    args = parser.parse_args(argv)
    corpus = corpus_mod.load(args.corpus)
    todo = [c for c in corpus.conversations(args.key or None) if c.words is None]

    def one(conversation: corpus_mod.Conversation) -> int:
        return len(ensure_words(conversation, record=True, private=not corpus.public))

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for conversation, count in zip(todo, pool.map(one, todo)):
            print(json.dumps({'key': conversation.key[:6], 'words': count}), flush=True)
    return 0


def gallery_for(corpus: corpus_mod.Corpus) -> dict[str, list[float]]:
    """Stored voiceprints (owner corpora), else the enrollment audio embedded through the peer with product code."""
    if corpus.gallery:
        return corpus.gallery
    from utils.stt.speaker_embedding import extract_embedding_from_bytes

    prints = {}
    for identity, path in corpus.gallery_audio().items():
        vector = extract_embedding_from_bytes(path.read_bytes(), f'{identity}.wav')
        if vector is not None:
            prints[identity] = [float(v) for v in vector.reshape(-1)]
    return prints


STORED_ARMS = {'production': ('conversation.json', None)}  # name -> (file, key inside it)


def stored_arms(corpus: corpus_mod.Corpus) -> dict[str, tuple[str, Optional[str]]]:
    """Every stored-label arm a private corpus carries: production's labels, and each ``diagnose --label L``
    result (``resolver_L.json``) as ``resolver_L`` (the resolver's labels) and ``final_L`` (the final pass's)."""
    arms = dict(STORED_ARMS)
    root = corpus.path / 'conversations'
    labels = sorted({p.stem.removeprefix('resolver_') for p in root.glob('*/resolver_*.json')}) if root.is_dir() else []
    for label in labels:
        arms[f'resolver_{label}'] = (f'resolver_{label}.json', 'segments')
        arms[f'final_{label}'] = (f'resolver_{label}.json', 'final_pass')
    return arms


def _stored_segments(conversation: corpus_mod.Conversation, source: tuple[str, Optional[str]]) -> Optional[list]:
    import json as _json

    path = conversation.path / source[0]
    if not path.is_file():
        return None
    value = _json.loads(path.read_text())
    if source[1] == 'final_pass':
        return ((value.get('final_pass') or {}).get('segments')) or None
    return value.get('segments') if isinstance(value, dict) else None


def stored_turns(words: list[dict], segments: Optional[list[dict]]) -> Optional[list[dict]]:
    """Stored segments on the audio clock, placed by their text: stored clocks are not on the audio clock
    (measured 2026-11-26 on an owner corpus: 17 % of segments within 1.5 s), so each stored token is aligned to
    the corpus words (``difflib``, no junk heuristic) and every aligned word takes its segment's labels. Words
    between two aligned words of one segment take it too; other words stay unlabeled (an abstention)."""
    import difflib
    import re

    if not segments:
        return None
    pattern = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
    stored_tokens, stored_owner = [], []
    for index, segment in enumerate(segments):
        for token in pattern.findall((segment.get('text') or '').lower()):
            stored_tokens.append(token)
            stored_owner.append(index)
    word_tokens, word_owner = [], []
    for index, word in enumerate(words):
        for token in pattern.findall((word.get('text') or '').lower()):
            word_tokens.append(token)
            word_owner.append(index)
    labels: list[Optional[int]] = [None] * len(words)
    matcher = difflib.SequenceMatcher(None, stored_tokens, word_tokens, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            labels[word_owner[block.b + k]] = stored_owner[block.a + k]
    last: dict[int, int] = {}
    for index, label in enumerate(labels):
        if label is None:
            continue
        previous = last.get(label)
        if previous is not None and all(labels[i] is None for i in range(previous + 1, index)):
            for i in range(previous + 1, index):
                labels[i] = label
        last[label] = index
    turns: list[dict] = []
    for word, label in zip(words, labels):
        if label is None:
            continue
        s = segments[label]
        if turns and turns[-1]['_segment'] == label and word['start'] - turns[-1]['end'] < 2.0:
            turns[-1]['end'] = max(turns[-1]['end'], word['end'])
            continue
        turns.append(
            {
                '_segment': label,
                'start': word['start'],
                'end': max(word['end'], word['start'] + 0.01),
                'speaker': s.get('speaker'),
                'speaker_id': s.get('speaker_id'),
                'speaker_id_scope': s.get('speaker_id_scope'),
                'is_user': bool(s.get('is_user')),
                'person_id': s.get('person_id'),
            }
        )
    for a, b in zip(turns, turns[1:]):
        if b['start'] < a['end']:
            a['end'] = b['start'] = (a['end'] + b['start']) / 2
    return [{k: v for k, v in t.items() if k != '_segment'} for t in turns if t['end'] > t['start']]


def owned_words(words: list[dict], segments: Optional[list[dict]]) -> Optional[set]:
    """Indexes of the words the conversation's own stored segments cover (text-aligned). A conversations-v3 row
    lists its recordings' whole audio files but owns only pieces of them; every arm is scored on these words."""
    turns = stored_turns(words, segments)
    if not turns:
        return None
    spans = [(t['start'], t['end']) for t in turns]
    return {i for i, w in enumerate(words) if any(a <= (w['start'] + w['end']) / 2 <= b for a, b in spans)}


def production_turns(conversation: corpus_mod.Conversation, words: Optional[list[dict]] = None) -> Optional[list[dict]]:
    """Production's stored labels on the audio clock (placed by text, see :func:`stored_turns`)."""
    if words is None:
        words = (conversation.words or {}).get('words') or []
    return stored_turns(words, (conversation.production or {}).get('segments'))


def run_arm(
    arm: Arm, jobs: list[dict], gallery: dict, peer_env: dict, work: Path, *, parallel: int = 1
) -> dict[str, dict]:
    """The arm's conversations split over ``parallel`` processes (each a fresh product import)."""
    from concurrent.futures import ThreadPoolExecutor

    shards = [jobs[i :: max(1, parallel)] for i in range(max(1, parallel))]
    shards = [s for s in shards if s]
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(shards) or 1) as pool:
        for part in pool.map(
            lambda pair: _run_shard(arm, pair[1], gallery, peer_env, work, pair[0]), list(enumerate(shards))
        ):
            results.update(part)
    return results


def _run_shard(arm: Arm, jobs: list[dict], gallery: dict, peer_env: dict, work: Path, index: int) -> dict[str, dict]:
    from testing.pipeline_lab.store import atomic_write_json

    backend = arm.backend or BACKEND
    job_path, out_path = work / f'job-{arm.name}-{index}.json', work / f'out-{arm.name}-{index}.jsonl'
    atomic_write_json(job_path, {'engine': arm.engine, 'conversations': jobs, 'gallery': gallery, 'out': str(out_path)})
    env = {k: os.environ[k] for k in PASS_ENV if k in os.environ}
    env.update(ISOLATION_ENV)
    env.update(peer_env)
    env.update(arm.env)
    env['PYTHONPATH'] = str(backend)
    python = os.environ.get('OMI_PIPELINE_LAB_ARM_PYTHON') or sys.executable
    done = subprocess.run(
        [python, str(RUNNER), str(job_path)], cwd=str(backend), env=env, capture_output=True, text=True
    )
    job_path.unlink(missing_ok=True)
    if done.returncode != 0:
        tail = '\n'.join(done.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f'arm {arm.name} exited {done.returncode}:\n{tail}')
    results = {}
    for line in out_path.read_text().splitlines():
        row = json.loads(line)
        results[row['key']] = row
    return results


def _out_dir(raw: Optional[str]) -> Path:
    from testing.pipeline_lab.scenario.paths import private_lab_root
    from testing.pipeline_lab.store import ensure_private_dir, private_dir

    if raw:
        return private_dir(Path(raw).expanduser(), 'speaker bench output')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root = ensure_private_dir(ensure_private_dir(private_lab_root() / 'speakers') / 'bench')
    return ensure_private_dir(root / stamp)


def bench(
    corpus: corpus_mod.Corpus,
    arms: list[Arm],
    *,
    mode: str = 'replay',
    record_words: bool = False,
    keys: Optional[list[str]] = None,
    out: Path,
    write_public_cassettes: bool = False,
    parallel: int = 1,
) -> dict:
    from testing.pipeline_lab.scenario.paths import private_lab_root
    from testing.pipeline_lab.store import atomic_write_bytes, ensure_private_dir

    started = time.monotonic()
    work = ensure_private_dir(out / 'work')
    conversations = list(corpus.conversations(keys))
    words = {c.key: ensure_words(c, record=record_words, private=not corpus.public) for c in conversations}
    store = CassetteStore(
        ensure_private_dir(ensure_private_dir(private_lab_root() / 'speakers') / 'cassettes'),
        write_public=write_public_cassettes and corpus.public,
    )
    jobs = []
    for c in conversations:
        pcm_path = work / f'{c.key}.pcm'
        atomic_write_bytes(pcm_path, c.pcm())
        jobs.append({'key': c.key, 'pcm_path': str(pcm_path), 'words': words[c.key], 'owner_reserved': False})
    report: dict[str, Any] = {
        'corpus': {'name': corpus.name, 'kind': 'public' if corpus.public else 'private', 'conversations': len(jobs)},
        'truth': sorted({(c.truth or {}).get('kind', 'none') for c in conversations}),
        'peer_mode': mode,
        'arms': {},
    }
    with SpeakerPeer(mode, store=store, workers=parallel) as peer:
        os.environ.update(peer.env())
        gallery = gallery_for(corpus)
        report['gallery'] = {'identities': len(gallery), 'owner': 'user' in gallery}
        outputs: dict[str, dict[str, dict]] = {}
        production = {c.key: production_turns(c, words[c.key]) for c in conversations}
        for name, source in ({} if corpus.public else stored_arms(corpus)).items():
            placed = {c.key: stored_turns(words[c.key], _stored_segments(c, source)) for c in conversations}
            if any(v is not None for v in placed.values()):
                outputs[name] = {k: {'key': k, 'segments': v} for k, v in placed.items() if v is not None}
                report['arms'][name] = {'engine': 'stored', 'source': source[0], 'env': {}, 'backend': None}
        for arm in arms:
            outputs[arm.name] = run_arm(arm, jobs, gallery, peer.env(), work, parallel=parallel)
            report['arms'][arm.name] = arm.describe()
        report['peer'] = peer.stats.summary()
    for job in jobs:
        Path(job['pcm_path']).unlink(missing_ok=True)
    # Pool every arm over the same conversations: those every arm labeled (stored arms can be partial).
    common = {c.key for c in conversations if c.truth}
    for results in outputs.values():
        common &= {k for k, row in results.items() if 'error' not in row}
    report['common_conversations'] = len(common)
    scopes = {c.key: owned_words(words[c.key], (c.production or {}).get('segments')) for c in conversations}
    for name, results in outputs.items():
        cards, agreements, errors, outcomes = {}, {}, 0, {}
        for c in conversations:
            row = results.get(c.key)
            if row is None:
                continue
            if 'error' in row:
                errors += 1
                continue
            outcome = (row.get('outcome') or {}).get('outcome')
            if outcome:
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
            if c.truth:
                cards[c.key] = score.score_conversation(words[c.key], c.truth, row['segments'], scopes.get(c.key))
            if name != 'production' and production.get(c.key) is not None:
                agreements[c.key] = score.agreement(words[c.key], production[c.key], row['segments'])
        report['arms'][name].update(
            pooled=score.pool(v for k, v in cards.items() if k in common) if common else None,
            pooled_all=score.pool(cards.values()) if cards else None,
            conversations=cards,
            agreement_with_production=agreements or None,
            errors=errors,
            outcomes=outcomes,
        )
    report['seconds'] = round(time.monotonic() - started, 1)
    from testing.pipeline_lab.store import atomic_write_json

    atomic_write_json(out / 'report.json', report)
    (out / 'summary.md').write_text(summary_markdown(report))
    return report


def _fmt(value: Any) -> str:
    if value is None:
        return '-'
    if isinstance(value, float):
        return f'{value:.3f}'
    return str(value)


def summary_markdown(report: dict) -> str:
    lines = [
        f"Speaker bench: corpus `{report['corpus']['name']}` ({report['corpus']['kind']}, "
        f"{report['corpus']['conversations']} conversations, truth {', '.join(report['truth'])}), "
        f"peer {report['peer_mode']}, {report['seconds']} s; pooled over the "
        f"{report.get('common_conversations')} conversations every arm labeled",
        '',
        '| arm | words | ' + ' | '.join(METRICS) + ' | errors |',
        '|---|---|' + '---|' * len(METRICS) + '---|',
    ]
    for name, arm in report['arms'].items():
        pooled = arm.get('pooled') or {}
        lines.append(
            f'| {name} | {_fmt(pooled.get("words"))} | '
            + ' | '.join(_fmt(pooled.get(m)) for m in METRICS)
            + f' | {arm.get("errors", 0)} |'
        )
    return '\n'.join(lines) + '\n'


def check_gates(report: dict, gates: list[str]) -> list[str]:
    """``ARM.METRIC>=VALUE`` / ``<=``; a missing metric fails."""
    failures = []
    for gate in gates:
        op = '>=' if '>=' in gate else '<='
        left, value = gate.split(op)
        arm, metric = left.split('.', 1)
        actual = ((report['arms'].get(arm) or {}).get('pooled') or {}).get(metric)
        if actual is None or (actual < float(value) if op == '>=' else actual > float(value)):
            failures.append(f'{gate} (actual {actual})')
    return failures


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog='python -m testing.pipeline_lab.speakers bench',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--arm', action='append', default=[], help='NAME[@BACKEND][:ENGINE][:K=V,...] (default: base)')
    parser.add_argument('--speakers', choices=('replay', 'record-local'), default='replay')
    parser.add_argument('--words', choices=('corpus', 'record-local'), default='corpus')
    parser.add_argument('--key', action='append', default=[], help='only these corpus conversations')
    parser.add_argument('--out', default=None)
    parser.add_argument('--gate', action='append', default=[], help='ARM.METRIC>=VALUE or ARM.METRIC<=VALUE')
    parser.add_argument('--write-public-cassettes', action='store_true', help='file new cassettes of a public corpus')
    parser.add_argument('--jobs', type=int, default=1, help='parallel arm processes (and local model workers)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        corpus = corpus_mod.load(args.corpus)
        arms = [Arm.parse(spec) for spec in (args.arm or ['base'])]
        out = _out_dir(args.out)
        report = bench(
            corpus,
            arms,
            mode=args.speakers,
            record_words=args.words == 'record-local',
            keys=args.key or None,
            out=out,
            write_public_cassettes=args.write_public_cassettes,
            parallel=args.jobs,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    failures = check_gates(report, args.gate)
    print(json.dumps({'out': str(out), 'gate_failures': failures}) if args.json else summary_markdown(report))
    if not args.json:
        print(f'report: {out}/report.json')
        for failure in failures:
            print(f'gate failed: {failure}')
    return 1 if failures else 0
