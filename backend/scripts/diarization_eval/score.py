#!/usr/bin/env python3
"""Print aggregate accuracy only; private words and speaker names never leave RAM."""

import argparse
import json
from pathlib import Path

from utils.stt.diarization_eval import score_turns, score_words
from utils.stt.diarization_turns import exclusive_from_activity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--turns', type=Path, help='JSON dict: conversation key -> exclusive turns')
    parser.add_argument(
        '--cached-activity-dir', type=Path, help='Read existing pyannote interval caches; crop/rebase locally'
    )
    parser.add_argument('--decision-mill', action='store_true', help='Read sibling conv_*.json word clocks')
    args = parser.parse_args()
    labels = json.loads(args.truth.read_text())
    turns = json.loads(args.turns.read_text()) if args.turns else None
    results = []
    for key, truth in labels.items():
        if args.decision_mill:
            words = json.loads((args.truth.parent / f'conv_{key}.json').read_text())['words']
            if len(words) != len(truth):
                raise ValueError('private truth/word count mismatch')
            entries = [{'start': w['s'], 'end': w['e'], 'speaker': t} for w, t in zip(words, truth)]
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
                result = score_turns(entries, turns[key])
            else:
                result = score_words(
                    entries, [str(w['pyannote']) if w['pyannote'] is not None else None for w in words]
                )
        else:
            result = score_turns(truth, turns[key])
        results.append(result)
    words = sum(r['words'] for r in results)
    print(
        json.dumps(
            {
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
    main()
