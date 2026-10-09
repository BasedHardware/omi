"""Arm, stratum and paired metrics from identical episode judgments."""

METRICS = (
    'informativeness_gap',
    'unsupported_claims',
    'wrong_provenance_claims',
    'unrelated_content_claims',
    'vacuous',
    'deterministic_vacuity',
    'faithfulness_pass',
)
COSTS = (
    'input_tokens',
    'output_tokens',
    'latency_seconds',
    'cached_tokens',
    'claim_tokens',
    'reasoning_tokens',
    'provider_cost',
)


def summarize(rows: list[dict]) -> dict:
    attempts = rows
    rows = [row for row in rows if row.get('status', 'ok') == 'ok']
    return {
        'count': len(rows),
        'attempted_count': len(attempts),
        'error_count': len(attempts) - len(rows),
        'mean_informativeness_gap': sum(row['informativeness_gap'] for row in rows) / len(rows) if rows else None,
        **{metric: sum(row[metric] for row in rows) for metric in METRICS if metric != 'informativeness_gap'},
        'property_failure_count': sum(len(row['property_failures']) for row in rows),
        'candidate_cost': {
            metric: {
                'measured_count': len(values),
                'total': sum(values) if values else None,
                'mean': sum(values) / len(values) if values else None,
            }
            for metric in COSTS
            for values in [
                [row['candidate_cost'].get(metric) for row in attempts if row['candidate_cost'].get(metric) is not None]
            ]
        },
    }


def arm_reports(rows: list[dict], arms: tuple[str, ...]) -> dict:
    return {
        arm: {
            'overall': summarize(group),
            'strata': {
                stratum: summarize([row for row in group if row['stratum'] == stratum])
                for stratum in sorted({row['stratum'] for row in group})
            },
        }
        for arm in arms
        for group in [[row for row in rows if row['arm'] == arm]]
    }


def paired_reports(rows: list[dict]) -> dict:
    by_arm = {(row['id'], row['arm']): row for row in rows if row.get('status', 'ok') == 'ok'}
    results = {}
    for comparison in ('baseline', 'stored'):
        pairs = []
        for episode in [row for row in rows if row['arm'] == 'episode' and row.get('status', 'ok') == 'ok']:
            other = by_arm.get((episode['id'], comparison))
            if other is None:
                continue
            pairs.append(
                {
                    'id': episode['id'],
                    'stratum': episode['stratum'],
                    'episode_minus_comparator': {
                        **{metric: float(episode[metric]) - float(other[metric]) for metric in METRICS},
                        'property_failure_count': len(episode['property_failures']) - len(other['property_failures']),
                        **{
                            metric: (
                                episode['candidate_cost'].get(metric) - other['candidate_cost'].get(metric)
                                if episode['candidate_cost'].get(metric) is not None
                                and other['candidate_cost'].get(metric) is not None
                                else None
                            )
                            for metric in COSTS
                        },
                    },
                }
            )
        if not pairs:
            continue

        def aggregate(group):
            return {
                'count': len(group),
                'mean_episode_minus_comparator': {
                    metric: sum(values) / len(values) if values else None
                    for metric in pairs[0]['episode_minus_comparator']
                    for values in [
                        [
                            pair['episode_minus_comparator'][metric]
                            for pair in group
                            if pair['episode_minus_comparator'][metric] is not None
                        ]
                    ]
                },
            }

        results[f'episode_vs_{comparison}'] = {
            'pairs': pairs,
            'overall': aggregate(pairs),
            'strata': {
                stratum: aggregate([pair for pair in pairs if pair['stratum'] == stratum])
                for stratum in sorted({pair['stratum'] for pair in pairs})
            },
            'direction': 'Negative gap/error/vacuity/property deltas favor episode; positive faithfulness favors episode.',
        }
    return results
