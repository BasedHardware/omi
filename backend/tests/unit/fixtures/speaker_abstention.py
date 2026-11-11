"""Fictional batch fixtures shared by display contracts and render evidence."""


def speaker_cases():
    def row(index, speaker_id, *, gap=False, wearer=False):
        return {
            'id': f'turn-{index}',
            'speaker': f'BATCH_UNASSIGNED_part_{speaker_id}' if gap else f'SPEAKER_{speaker_id}',
            'speaker_id': speaker_id,
            'speaker_id_scope': 'final:batch:fictional',
            'speaker_match_source': 'batch_abstention' if gap else None,
            'speaker_identity_status': 'ambiguous' if gap else 'unknown',
            'is_user': wearer,
            'speaker_label_source': 'manual' if wearer else None,
            'text': [
                'Let us plan the garden.',
                'The seedlings arrive Friday.',
                'We can plant on Saturday.',
                'I will bring the tools.',
            ][index],
            'start': index * 6.0,
            'end': (index + 1) * 6.0,
        }

    cases = {
        'one-voice': ([row(0, 0), row(1, 1, gap=True), row(2, 2, gap=True)], [0]),
        'two-voices': ([row(0, 0), row(1, 1, gap=True), row(2, 2), row(3, 3, gap=True)], [0, 2]),
        'wearer': ([row(0, 0, wearer=True), row(1, 1, gap=True), row(2, 2, gap=True)], [0]),
    }

    epoch_rows, ids = cases['two-voices']
    cases['mixed-epochs'] = (
        [dict(r, speaker_id_scope=f"capture:epoch-{i // 2}") for i, r in enumerate(epoch_rows)],
        ids[:],
    )
    point_rows, ids = cases['one-voice']
    cases['point-keys'] = (
        [
            dict(r, end=r['start'], speaker=f'BATCH_UNASSIGNED_part_point_{i}') if i else dict(r)
            for i, r in enumerate(point_rows)
        ],
        ids[:],
    )
    cases['historical-fallback'] = (
        [
            dict(point_rows[0]),
            dict(point_rows[1], speaker='BATCH_UNASSIGNED_oldID_1', speaker_id=-1, speaker_match_source=None),
            dict(point_rows[2], speaker='BATCH_UNASSIGNED_oldID_2', speaker_id=-1, speaker_match_source=None),
        ],
        [0],
    )
    return cases
