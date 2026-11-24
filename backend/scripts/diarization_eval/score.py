#!/usr/bin/env python3
"""Print aggregate accuracy only; private words and speaker names never leave RAM."""

import argparse
import json
from pathlib import Path

from utils.stt.diarization_eval import aggregate_scorecards, score_recording, score_turns, score_words
from utils.stt.diarization_turns import exclusive_from_activity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--turns', type=Path, help='JSON dict: conversation key -> exclusive turns')
    parser.add_argument(
        '--cached-activity-dir', type=Path, help='Read existing pyannote interval caches; crop/rebase locally'
    )
    parser.add_argument('--decision-mill', action='store_true', help='Read sibling conv_*.json word clocks')
    parser.add_argument('--identity-table', type=Path, help='Predeclared truth label -> owner/person identity JSON')
    parser.add_argument('--model-references', type=Path, help='Recording key -> model reference text JSON (not truth)')
    parser.add_argument('--exclusions', type=Path, help='Recording key -> enrollment exclusion spans JSON')
    parser.add_argument('--crop-start', type=float, default=0.0, help='Offset to add to turn clocks')
    args = parser.parse_args()
    identities = json.loads(args.identity_table.read_text()) if args.identity_table else None
    references = json.loads(args.model_references.read_text()) if args.model_references else {}
    exclusions = json.loads(args.exclusions.read_text()) if args.exclusions else {}
    if identities is not None and (args.cached_activity_dir or not args.turns):
        parser.error('strict identity scoring requires actual persisted --turns')
    labels = json.loads(args.truth.read_text())
    turns = json.loads(args.turns.read_text()) if args.turns else None
    results = []
    for key, truth in labels.items():
        if args.decision_mill:
            words = json.loads((args.truth.parent / f'conv_{key}.json').read_text())['words']
            if len(words) != len(truth):
                raise ValueError('private truth/word count mismatch')
            entries = [
                {'start': w['s'], 'end': w['e'], 'speaker': t, **({'text': w['text']} if 'text' in w else {})}
                for w, t in zip(words, truth)
            ]
            if args.cached_activity_dir:
                conv = json.loads((args.truth.parent / f'conv_{key}.json').read_text())
                files = list(args.cached_activity_dir.glob(key + '*.json'))
                if len(files) != 1:
                    raise ValueError('expected one cached activity result per conversation')
                activity = json.loads(files[0].read_text())['intervals']
                raw = [
                    {
                        'start': max(0, t['start_s'] - conv['t0']),
                        'end': min(conv['dur'], t['end_s'] - conv['t0']),
                        'speaker': t['channel_id'],
                    }
                    for t in activity
                    if t['end_s'] > conv['t0'] and t['start_s'] < conv['t0'] + conv['dur']
                ]
                result = score_turns(entries, exclusive_from_activity(raw))
            elif turns:
                result = score_turns(entries, turns[key]) if identities is None else None
            else:
                result = score_words(
                    entries, [str(w['pyannote']) if w['pyannote'] is not None else None for w in words]
                )
        else:
            result = score_turns(truth, turns[key]) if identities is None else None
        if identities is not None:
            result = score_recording(
                entries if args.decision_mill else truth,
                turns[key],
                identities,
                crop_start=args.crop_start,
                excluded_spans=exclusions.get(key, ()),
                model_reference=references.get(key),
            )
        results.append(result)
    if identities is not None:
        print(json.dumps({'per_recording': results, 'pooled': aggregate_scorecards(results)}, indent=2))
        return
    words = sum(r['words'] for r in results)
    print(
        json.dumps(
            {
                'metric_kind': 'hungarian_oracle_diagnostic_not_automatic_identity',
                'conversations': len(results),
                'scored_conversations': sum(r['words'] > 0 for r in results),
                'per_conversation': results,
                'pooled_1to1': sum(r['correct_1to1'] for r in results) / words if words else None,
                'pooled_many_to_1': sum(r['correct_many_to_1'] for r in results) / words if words else None,
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # File/JSON exceptions can embed private paths or transcript fragments.
        # Only a low-cardinality exception class may leave the local process.
        import sys

        print(json.dumps({'status': 'FAILED', 'exception_type': type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
