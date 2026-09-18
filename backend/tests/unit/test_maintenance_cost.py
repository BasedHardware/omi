from utils.memory.maintenance_cost import estimate_pass, usd_for_tokens


def test_flex_is_half_of_standard_short_context_rates():
    assert usd_for_tokens(1_000_000, 1_000_000, flex=False) == 1.40
    assert usd_for_tokens(1_000_000, 1_000_000, flex=True) == 0.70


def test_average_user_folds_required_items_into_one_consolidation_batch():
    estimate = estimate_pass(pending_l2=1, pending_consolidation=3, flex=True)
    assert estimate.l2_calls == 0
    assert estimate.consolidation_calls == 1
    assert estimate.usd == usd_for_tokens(8_000, 1_200, flex=True)


def test_heavy_user_batches_twenty_and_issues_no_standalone_l2():
    estimate = estimate_pass(pending_l2=20, pending_consolidation=15, flex=True)
    assert estimate.l2_calls == 0
    assert estimate.consolidation_calls == 2
    assert estimate.usd == usd_for_tokens(16_000, 2_400, flex=True)


def test_exactly_twenty_pending_items_is_one_cached_call():
    estimate = estimate_pass(pending_l2=0, pending_consolidation=20, flex=True)
    assert estimate.consolidation_calls == 1
    estimate = estimate_pass(pending_l2=1, pending_consolidation=20, flex=True)
    assert estimate.consolidation_calls == 2
