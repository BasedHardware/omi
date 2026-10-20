from datetime import datetime, timedelta, timezone

import pytest

from scripts.report_mentor_usefulness import report

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
START = NOW - timedelta(days=9)
END = NOW - timedelta(days=2)


def item(score, acted=False, negative=False, **patch):
    row = dict(
        producer='conversation_mentor_v2',
        producer_version=1,
        created_at=START,
        delivered=True,
        delivered_at=START + timedelta(hours=1),
        usefulness_score=score,
        acted_24h=acted,
        negative=negative,
    )
    return dict(row, **patch)


def readout(rows, **patch):
    arguments = dict(cohort_start=START, cohort_end=END, now=NOW, thresholds=[0.5])
    return report(rows, **dict(arguments, **patch))


def test_auc_ties_threshold_equality_and_independent_negative_join():
    rows = [item(0.9, True), item(0.5, True, True), item(0.5), item(0.1, negative=True)]
    result = readout(rows)
    assert result['acted_auc'] == 0.875
    assert result['negative_auc'] == 0.125
    split = result['by_threshold'][0]
    assert split['kept']['deliveries'] == 3
    assert split['kept']['acted_rate'] == 2 / 3
    assert split['kept']['negative_rate'] == 1 / 3
    assert split['dropped']['deliveries'] == 1
    assert split['dropped']['acted_rate'] == 0
    assert split['dropped']['negative_rate'] == 1


def test_only_mature_delivered_mentor_cohort_is_evaluated_missing_scores_counted():
    result = readout(
        [
            item(0.8, True),
            item(None),
            item(float('nan')),
            item(True),
            item(0.1, delivered=False),
            item(0.1, created_at=END),
            item(0.1, created_at=START - timedelta(seconds=1)),
            item(0.1, delivered_at=NOW - timedelta(hours=23)),
            item(0.1, producer='commitment_followup'),
            item(0.1, producer_version=2),
        ]
    )
    assert result['mature_deliveries'] == 4
    assert result['missing_score_deliveries'] == 3
    assert result['scored']['deliveries'] == 1
    assert result['acted_auc'] is None and result['negative_auc'] is None
    assert result['by_threshold'][0]['dropped']['acted_rate'] is None


@pytest.mark.parametrize('threshold', [-0.1, 1.1, float('nan'), True])
def test_invalid_thresholds_cannot_produce_a_readout(threshold):
    with pytest.raises(ValueError, match='invalid threshold'):
        readout([], thresholds=[threshold])


def test_incomplete_creation_cohort_and_naive_timestamps_rejected():
    with pytest.raises(ValueError, match='48 hours'):
        readout([], cohort_end=NOW - timedelta(hours=47))
    with pytest.raises(ValueError, match='timezone-aware'):
        readout([item(0.5, created_at=START.replace(tzinfo=None))])


def test_exported_utc_timestamps_and_no_classes_are_handled():
    row = item(0.5, True)
    row.update(created_at=START.isoformat(), delivered_at=START.isoformat().replace('+00:00', 'Z'))
    result = readout([row], thresholds=[0, 1])
    assert result['acted_auc'] is None
    assert result['by_threshold'][0]['kept']['acted_rate'] == 1
    assert result['by_threshold'][1]['kept']['acted_rate'] is None
