"""Why production's speaker resolver abstains: run today's resolver read-only on the owner's own conversations.

    python -m testing.pipeline_lab.speakers diagnose --guard <guard.py> --uid-file <0600> --secret-file <0600> \\
        --corpus owner-60d [--speakers record-local]

For every conversation of an owner corpus (``owner_export.py``), this reads the production conversation again
and runs ``utils.conversations.speaker_resolution.resolve_speakers_for_processing`` in this process, with:

- production's ``backend-sync`` flags from this checkout's ``deploy/runtime_env.yaml`` (secrets and endpoints
  dropped; bucket names stay the code defaults);
- every Firestore, Storage and Redis write refused (``v3.prod_export.read_only_fence``); the resolver's own cache
  upload and speaker-evidence write are replaced by no-ops so a refused write cannot masquerade as a reason;
- model calls sent to the lab's speaker peer (``HOSTED_*`` URLs), never the hosted diarizer;
- the whole-conversation final pass not run (its staged artifacts expire 24 h after projection).

It writes ``<conversation>/resolver_today.json`` in the private corpus: the resolver's reason trail, the
resulting resolution status, and the labels it produced (stored-clock segments with identity fields), which the
bench scores as the ``resolver_today`` arm. Prints per-conversation reasons and counts only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from unittest import mock

from testing.pipeline_lab.speakers import corpus as corpus_mod
from testing.pipeline_lab.speakers.owner_export import SEGMENT_FIELDS, _plain, corpus_key
from testing.pipeline_lab.v3.prod_export import load_guard, read_only_fence
import yaml
from testing.pipeline_lab.stack.runtime_env import ENDPOINTISH, SECRETISH, _scalar, _service_env
from models.conversation import Conversation
from testing.pipeline_lab.speakers.peer import SpeakerPeer
from testing.pipeline_lab.scenario.paths import private_lab_root
from testing.pipeline_lab.store import ensure_private_dir

BACKEND = Path(__file__).resolve().parents[3]


def production_flags(service: str = 'backend-sync') -> dict[str, str]:

    document = yaml.safe_load((BACKEND / 'deploy' / 'runtime_env.yaml').read_text(encoding='utf-8'))
    env = {}
    for key, entry in _service_env(document, 'prod', service).items():
        value = _scalar(entry)
        if value is None or SECRETISH.search(key) or ENDPOINTISH.search(key):
            continue
        env[key] = value
    return env


def _ids_by_key(uid: str, salt: str, days: int) -> dict[str, str]:
    from database import conversations as conversations_db

    end = datetime.now(timezone.utc)
    out, offset = {}, 0
    while True:
        page = conversations_db.get_conversations(
            uid, limit=100, offset=offset, start_date=end - timedelta(days=days), end_date=end, metadata_only=True
        )
        for meta in page:
            out[corpus_key(salt, str(meta['id']))] = str(meta['id'])
        if len(page) < 100:
            return out
        offset += 100


def final_pass(uid: str, conversation: Any, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """The staged-unit whole-conversation pass (``final_pass_batch._run``), read-only: budget reservation and
    recurring-voice learning are off (both write), and the applied labels are captured before persistence."""
    from utils.conversations import final_pass_batch
    from utils.conversations.speaker_resolution import apply_speaker_resolution, load_voiceprints_for_resolution

    captured: dict[str, Any] = {}

    def apply(candidate, *args, **kwargs):
        apply_speaker_resolution(candidate, *args, **kwargs)
        captured['segments'] = [
            {field: _plain(segment).get(field) for field in SEGMENT_FIELDS} for segment in candidate.transcript_segments
        ]

    with mock.patch.object(final_pass_batch, '_reserve_budget', lambda seconds: True), mock.patch.object(
        final_pass_batch, 'recurring_enabled_for', lambda *a, **k: False
    ):
        try:
            result = final_pass_batch._run(
                uid,
                conversation.model_copy(deep=True),
                receipt,
                load_voiceprints_for_resolution,
                apply,
                final_pass_batch.UnitFailureContext(),
            )
            outcome = dict(result) if isinstance(result, Mapping) else {'outcome': str(result)}
        except Exception as exc:
            from utils.conversations.final_pass_errors import error_details

            details = error_details(exc)
            reason = getattr(exc, 'reason', None) or getattr(exc, 'outcome', None) or details.get('reason')
            outcome = {
                'outcome': 'raised',
                'exception_type': type(exc).__name__,
                'reason': str(reason or '')[:60],
                'location': str(details.get('location') or '')[:120],
            }
    scalar = (str, int, float, bool, type(None))
    # Counts (coverage, coverage_reasons, split_refusals) are kept: aggregates, never text or ids.
    outcome = {
        k: v
        for k, v in outcome.items()
        if isinstance(v, scalar) or (isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values()))
    }
    return {**outcome, 'applied': 'segments' in captured, 'segments': captured.get('segments')}


def diagnose(uid: str, conversation_id: str, *, run_final_pass: bool = False) -> dict[str, Any]:
    from database import conversations as conversations_db
    from utils.conversations import speaker_resolution

    reasons: list[str] = []
    real_reason = speaker_resolution.resolver_reason

    def record(reason: str) -> None:
        reasons.append(reason)
        real_reason(reason)

    abstentions: list[str] = []
    real_without = speaker_resolution._without_resolution

    def without(conversation, *args, **kwargs):
        abstentions.append(str(kwargs.get('reason') or (args[0] if args else '')))
        return real_without(conversation, *args, **kwargs)

    raw = conversations_db.get_conversation(uid, conversation_id)
    conversation = Conversation(**raw)
    with mock.patch.object(speaker_resolution, 'resolver_reason', record), mock.patch.object(
        speaker_resolution, '_without_resolution', without
    ), mock.patch.object(speaker_resolution, 'upload_speaker_embedding_cache', lambda *a, **k: None), mock.patch.object(
        speaker_resolution.speaker_evidence, 'finish', lambda *a, **k: None
    ):
        error = None
        try:
            speaker_resolution.resolve_speakers_for_processing(
                uid, conversation, final_pass_runner=lambda *a, **k: None
            )
        except Exception as exc:  # a diagnosis, not a gate: record and continue
            error = f'{type(exc).__name__}'
    resolution = conversation.speaker_resolution
    final = None
    if run_final_pass:
        from database import conversations as conversations_db

        # Production order: the whole pass runs on the conversation the resolver just labeled.
        final = final_pass(uid, conversation, conversations_db.get_manual_speaker_receipt(uid, conversation_id))
    segments = []
    for segment in conversation.transcript_segments:
        data = _plain(segment)
        segments.append({field: data.get(field) for field in SEGMENT_FIELDS})
    return {
        'reasons': [r for r in reasons if r != 'disabled'],
        'abstentions': abstentions,
        'status': getattr(resolution, 'status', None),
        'coverage': getattr(resolution, 'coverage', None),
        'error': error,
        'segments': segments,
        'final_pass': final,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.speakers diagnose', description=__doc__)
    parser.add_argument('--guard', required=True)
    parser.add_argument('--uid-file', required=True)
    parser.add_argument('--secret-file', required=True)
    parser.add_argument('--corpus', default=None)
    parser.add_argument('--days', type=int, default=90, help='window searched for the corpus conversations')
    parser.add_argument('--speakers', choices=('replay', 'record-local'), default='record-local')
    parser.add_argument('--key', action='append', default=[])
    parser.add_argument('--final-pass', action='store_true', help='also run the staged-unit final pass (read-only)')
    parser.add_argument(
        '--without-source-recordings',
        action='store_true',
        help='refuse receipts naming v3 source recordings (origin/main behaviour before the v3 receipt fix)',
    )
    parser.add_argument('--recent', type=int, default=0, help='diagnose the N newest conversations instead of a corpus')
    parser.add_argument('--out', default=None, help='with --recent: a private directory for the results')
    parser.add_argument('--label', default='today', help='corpus mode: results go to resolver_<label>.json')
    args = parser.parse_args(argv)

    guard = load_guard(args.guard)
    uid = guard.owner_uid(args.uid_file)
    guard.load_secret(args.secret_file)
    os.environ.update(production_flags())
    totals: Counter = Counter()
    patches = []
    if args.without_source_recordings:
        from utils.conversations import final_pass_batch

        patches.append(mock.patch.object(final_pass_batch, 'receipt_sources', lambda conversation: ()))
    for patch in patches:
        patch.start()
    try:
        with SpeakerPeer(args.speakers) as peer, read_only_fence():
            os.environ.update(peer.env())
            for key, conversation_id, target in _targets(uid, args):
                result = diagnose(uid, conversation_id, run_final_pass=args.final_pass)
                corpus_mod.write_json(target, result, private=True)
                final = result.get('final_pass') or {}
                totals['status:' + str(result['status'])] += 1
                for reason in set(result['reasons']):
                    totals['reason:' + reason] += 1
                if args.final_pass:
                    totals['final_pass:' + str(final.get('outcome'))] += 1
                    totals['final_pass_applied'] += bool(final.get('applied'))
                    totals['final_pass_split_segments'] += int(final.get('split_segments') or 0)
                    for reason, count in (final.get('split_refusals') or {}).items():
                        totals['split_refused:' + reason] += count
                print(
                    json.dumps(
                        {
                            'key': key[:6],
                            'status': result['status'],
                            'reasons': result['reasons'][-4:],
                            'abstentions': result['abstentions'][-3:],
                            'error': result['error'],
                            'owner_segments': sum(1 for s in result['segments'] if s.get('is_user')),
                            'final_pass': {
                                k: final.get(k)
                                for k in (
                                    'outcome',
                                    'reason',
                                    'location',
                                    'applied',
                                    'split_segments',
                                    'split_refusals',
                                )
                            }
                            or None,
                            'final_owner_segments': sum(1 for s in final.get('segments') or [] if s.get('is_user')),
                        }
                    ),
                    flush=True,
                )
            print(json.dumps({'peer': peer.stats.summary()}))
    finally:
        for patch in patches:
            patch.stop()
    print(json.dumps(dict(sorted(totals.items()))))
    return 0


def _targets(uid: str, args: Any):
    """(key, conversation id, result path): a corpus's conversations, or the newest v3 conversations."""
    if args.recent:
        from database import conversations as conversations_db

        root = ensure_private_dir(ensure_private_dir(private_lab_root() / 'speakers') / 'diagnose')
        out = ensure_private_dir(Path(args.out).expanduser() if args.out else root / 'recent')
        salt_file = root / 'salt'
        if not salt_file.exists():
            salt_file.write_text(os.urandom(16).hex())
            salt_file.chmod(0o600)
        salt = salt_file.read_text()
        end = datetime.now(timezone.utc)
        page = conversations_db.get_conversations(
            uid, limit=200, start_date=end - timedelta(days=args.days), end_date=end, metadata_only=True
        )
        found = 0
        for meta in page:
            if found >= args.recent:
                return
            raw = conversations_db.get_conversation(uid, meta['id']) or {}
            if raw.get('discarded') or raw.get('deleted') or not raw.get('v3_recording_ids'):
                continue
            if not any(
                (s.get('speaker_id_scope') or '').startswith('final:batch:')
                for s in raw.get('transcript_segments') or []
            ):
                continue
            found += 1
            key = corpus_key(salt, str(meta['id']))
            yield key, str(meta['id']), out / f'{key}.json'
        return
    corpus = corpus_mod.load(args.corpus)
    if corpus.public:
        raise SystemExit('diagnose reads production; it takes an owner corpus')
    ids = _ids_by_key(uid, (corpus.path / 'salt').read_text(), args.days)
    for conversation in corpus.conversations(args.key or None):
        conversation_id = ids.get(conversation.key)
        if conversation_id is None:
            print(json.dumps({'key': conversation.key[:6], 'missing': True}))
            continue
        yield conversation.key, conversation_id, conversation.path / f'resolver_{args.label}.json'


if __name__ == '__main__':
    raise SystemExit(main())
