from config.proactivity_v2 import producer_for
from database.proactivity import metric_verdict


def test_maturity_sample_cost_and_unknown_guards():
    producer = producer_for('commitment_followup')
    totals = dict(delivered_count=199, acted_count=0, negative_count=0, charged_micro_usd=50000, unknown_count=0)
    assert metric_verdict(producer, totals) == 'collecting'
    totals['delivered_count'] = 200
    assert metric_verdict(producer, totals) == 'killed'
    totals['acted_count'] = 20
    totals['charged_micro_usd'] = 5000000
    assert metric_verdict(producer, totals) == 'passing'
    totals['charged_micro_usd'] += 1
    assert metric_verdict(producer, totals) == 'killed'
    totals['unknown_count'] = 1
    assert metric_verdict(producer, totals) == 'unknown'


def test_low_engagement_still_latches_kill_with_unknown_cost():
    totals = dict(delivered_count=200, acted_count=19, negative_count=0, charged_micro_usd=0, unknown_count=1)
    assert metric_verdict(producer_for('commitment_followup'), totals) == 'killed'
    totals.update(acted_count=20, unknown_count=0, negative_count=200)
    assert metric_verdict(producer_for('commitment_followup'), totals) == 'passing'
