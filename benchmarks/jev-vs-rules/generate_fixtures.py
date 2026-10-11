#!/usr/bin/env python3
"""Deterministic synthetic challenge families; provisional labels precede replay.

Freeze manifest before paid scoring. Labels require David/language review.
Families are independent test scenarios, not independent sampled observations.
"""

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def generate():
    spec = importlib.util.spec_from_file_location('harness', HERE / 'harness.py')
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    filler = [
        ('ummmmmm', 'discard', 'en', 'elongated hesitation'),
        ('uhhhhh', 'discard', 'en', 'elongated hesitation'),
        ('hmmmmmm', 'discard', 'en', 'elongated hesitation'),
        ('ahhhhh', 'discard', 'en', 'elongated reaction'),
        ('ohhhhh', 'uncertain', 'en', 'reaction intent unavailable'),
        ('mmmmmmmm', 'discard', 'en', 'hesitation only'),
        ('hahahahaha', 'uncertain', 'en', 'laughter might mark social interaction'),
        ('heh hehehe', 'discard', 'en', 'no retrievable statement'),
        ('right', 'uncertain', 'en', 'assent without context'),
        ('right right right', 'discard', 'en', 'repeated backchannels'),
        ('yeah okay', 'discard', 'en', 'backchannels only'),
        ('dạ', 'uncertain', 'vi', 'Vietnamese assent requires language reviewer'),
        ('dạ vâng', 'uncertain', 'vi', 'polite assent without antecedent'),
        ('はい', 'uncertain', 'ja', 'Japanese assent requires language reviewer'),
        ('はいはい', 'uncertain', 'ja', 'repeated Japanese assent'),
        ('嗯嗯', 'discard', 'zh', 'acknowledgement pattern; review required'),
        ('好的', 'uncertain', 'zh', 'assent without context'),
        ('oui ouais', 'discard', 'fr', 'backchannels only; review required'),
        ('да угу', 'discard', 'ru', 'backchannels only; review required'),
        ('sí vale', 'uncertain', 'es', 'assent without context'),
        ("don't go", 'keep', 'en', 'safety prohibition'),
        ('stop', 'keep', 'en', 'standalone safety instruction'),
        ('do not go', 'keep', 'en', 'explicit prohibition'),
        ('"remind me to stop"', 'keep', 'en', 'quoted reminder still retrievable'),
        ('"note to self: do not go"', 'keep', 'en', 'quoted safety reminder'),
        ('no', 'uncertain', 'en', 'negative answer without question'),
        ('yes', 'uncertain', 'en', 'answer without question'),
        ('um ' * 101, 'discard', 'en', 'long filler must not become content'),
        ('dạ, mai gọi mẹ', 'keep', 'vi', 'call mother tomorrow; review translation'),
        ('はい、明日電話します', 'keep', 'ja', 'commitment to call tomorrow; review translation'),
    ]
    function = []
    starters = ['i', 'you', 'we', 'they', 'it', 'this', 'that', 'there', 'here', 'what']
    for starter in starters:
        for count in (24, 25, 26):
            head = starter
            tail = ' '.join(['and'] * (count - 1))
            # Distinct antecedent/generic function scenarios, with protective mutations.
            index = len(function)
            if index in (3, 9, 15):
                tail = tail.rsplit(' ', 1)[0] + ' 7'
                label, reason = 'keep', 'digit protects a retrievable identifier'
            elif index in (6, 12, 18):
                tail = tail.rsplit(' ', 1)[0] + ' Will'
                label, reason = 'keep', 'capitalized name homograph'
            elif index in (21, 24):
                tail = tail.rsplit(' ', 1)[0] + ' AND'
                label, reason = 'uncertain', 'casing protects ambiguous ASR'
            elif index == 27:
                head = 'May'
                label, reason = 'keep', 'initial month or name homograph'
            else:
                label, reason = 'discard', f'{count} function tokens, no referent or statement'
            function.append((head + ' ' + tail, label, 'en', reason))
    scraps = []
    noise = ['um', 'uh okay', 'right right', 'hmm', 'yeah yeah', 'oh um', 'dạ', 'はい', 'okay cool', 'mmm']
    commitments = [
        "don't go",
        'stop',
        'we agree',
        'I will',
        'go now',
        'stay here',
        'wait',
        'not now',
        'keep it',
        'hold on',
    ]
    for i in range(10):
        scraps.append(
            (
                noise[i],
                'discard',
                'en' if i not in (6, 7) else ('vi' if i == 6 else 'ja'),
                'noise inside synthetic Friday Coffee and Cowork event',
                True,
            )
        )
        scraps.append((commitments[i], 'keep', 'en', 'useful short instruction/commitment inside event', True))
        scraps.append((noise[i] + ' ' + noise[(i + 1) % 10], 'discard', 'en', 'noise outside event', False))
    rows = []
    for rule, entries in [('R03', filler), ('R08', function), ('R16', scraps)]:
        for i, entry in enumerate(entries, 1):
            text, label, language, reason = entry[:4]
            row = dict(
                family_id=f'{rule}-{i:02}',
                rule_ids=[rule],
                segments=[text.strip()],
                language=language,
                source_kind='live' if i % 2 else 'sync',
                trigger='capture_end',
                keep_label=label,
                reason=reason,
                provenance='synthetic',
                label_status='agent_proposed_unreviewed',
            )
            if rule == 'R16':
                row['calendar'] = (
                    dict(
                        title='Friday Coffee and Cowork',
                        event_window=[0, 7200],
                        conversation_window=[100, 120],
                        overlap_seconds=20,
                        event_coverage=20 / 7200,
                        conversation_coverage=1,
                        status='confirmed',
                        response='accepted',
                    )
                    if entry[4]
                    else None
                )
            row['expected_baseline'] = h.baseline(row)
            # Assert independently specified nomination expectation, not a circular baseline comparison.
            rule_verdict, rule_reason = h.runtime()['utils.conversations.relevance_rules'].deterministic_relevance(
                row['segments'], None
            )
            if rule == 'R03' and i <= 20 or rule == 'R03' and i == 28:
                assert (rule_verdict, rule_reason) == ('discard', 'filler_only'), row['family_id']
            if rule == 'R08' and label == 'discard':
                expected = ('discard', 'no_content_words') if len(text.split()) <= 25 else (None, 'ambiguous')
                assert (rule_verdict, rule_reason) == expected, row['family_id']
            if rule == 'R16':
                assert rule_verdict == 'discard', row['family_id']
                row['expected_without_calendar'] = h.baseline(row, without_calendar=True)
                assert row['expected_baseline']['verdict'] == ('keep' if entry[4] else 'discard')
            rows.append(row)
    return rows


if __name__ == '__main__':
    rows = generate()
    (HERE / 'fixtures/manifest.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    print(f'Wrote {len(rows)} synthetic families; generator rule assertions passed.')
