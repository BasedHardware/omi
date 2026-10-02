import json

from scripts.jev_capture_shadow_readout import _record, _upper_false_rate, readout


def test_log_export_readout_joins_outcomes_and_uses_exact_bound():
    decision = {
        'event': 'jev_capture_shadow',
        'id': 's1',
        'uid': 'u',
        'decision': 'same_scene',
        'first_id': 'a',
        'second_id': 'b',
        'category': 'cross_source',
        'rule_fold': False,
        'would_decide': True,
        'p': 0.8,
        'latency_seconds': 0.5,
    }
    outcome = {
        'event': 'jev_capture_shadow_outcome',
        'uid': 'u',
        'action': 'manual_merge',
        'conversation_ids': ['a', 'b'],
    }
    assert _record('jev_capture_shadow ' + json.dumps(decision)) == decision
    result = readout([decision, outcome], {'s1': True})
    assert result['agreement']['cross_source:jev_only'] == 1
    assert result['outcome_proxies']['manual_merge:would_fold'] == 1
    assert result['labels']['missed_fold_rate'] == 0
    unavailable = {**decision, 'id': 's2', 'p': None, 'would_decide': None, 'outcome': 'timeout'}
    with_timeout = readout([decision, unavailable, outcome])
    assert with_timeout['volumes']['same_scene:cross_source'] == 2
    assert with_timeout['attempt_outcomes']['same_scene:timeout'] == 1
    assert with_timeout['agreement']['cross_source:jev_only'] == 1
    assert _upper_false_rate(0, 299) < 0.01
    assert _upper_false_rate(0, 298) > 0.01
