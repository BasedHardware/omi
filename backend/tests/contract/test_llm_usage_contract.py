"""Dual-backend contract for LLM usage accounting (ADR-0044 facade + ADR-0002 store port).

`database/llm_usage.py` is small and carries three shapes the facade has to translate, two of them in
variants nothing else exercises:

    atomic_field_ops   Increment on DOTTED field paths — ``f"{feature}.{model}.input_tokens"`` — so the
                       backend has to create nested structure and add into it, not set a key with a dot
                       in its name
    collection_group   get_global_top_features sweeps every user's `llm_usage` subcollection with a
                       RANGE filter (``date >= cutoff``), not the equality the finalization sweep uses
    transaction        record_chat_quota_question writes an idempotency event and increments the counter
                       in one transaction, so a retried question cannot double-count a user's quota

This is money and quota, which is why it is worth proving rather than assuming: an increment that lands
as a set makes every user look like they asked one question, and a group query that misses a parent
under-reports usage without failing.

**A measured divergence lives here, and these tests pin it instead of hiding it** (BACKLOG L50). The
writes use ``set(..., merge=True)`` with dotted keys. Real Firestore does NOT treat a dot as a path in
``set`` — only ``update`` does — so it stores a field literally named ``chat.model.input_tokens``. Our
Mongo facade nests it. The value accumulates correctly on BOTH, and that invariant is asserted on both;
the SHAPE differs, and the shape is what ``_aggregate_summary`` reads, so ``get_usage_summary`` works on
Mongo and returns ``{}`` on Firestore. Which side is right is a decision, not a mechanical fix: our
behaviour matches the reader's evident intent, Firestore matches the documented letter of ``set``.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

TODAY = datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _counter(daily: dict, *path: str) -> int:
    """Read a counter under EITHER shape — nested (Mongo) or a literal dotted key (Firestore).

    Deliberately not a normalization the tests hide behind: the divergence has its own test below. This
    exists so the tests about ACCUMULATION and IDEMPOTENCE can assert what they are about on both
    backends, instead of failing for an unrelated reason.
    """
    flat = '.'.join(path)
    if flat in daily:
        return int(daily[flat])
    node = daily
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return 0
        node = node[key]
    return int(node)


@pytest.fixture
def usage(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'usage-{run}'
    written: list[str] = []

    yield {'uid': uid, 'run': run, 'store': bind_store, 'written': written}

    for path in written:
        bind_store.delete(path)
    bind_store.delete(f'users/{uid}/llm_usage/{TODAY}')


# --- atomic field ops on dotted paths -------------------------------------------------------------


def test_repeated_usage_adds_up(usage):
    """Three calls for the same feature+model must total, not overwrite. This is the invariant the
    Increment exists for, and it holds on both backends whatever shape the field lands in."""
    import database.llm_usage as usage_db

    for _ in range(3):
        usage_db.record_llm_usage(usage['uid'], 'chat', 'model-a', input_tokens=10, output_tokens=4)

    daily = usage_db.get_daily_usage(usage['uid'])

    assert _counter(daily, 'chat', 'model-a', 'input_tokens') == 30
    assert _counter(daily, 'chat', 'model-a', 'output_tokens') == 12
    assert _counter(daily, 'chat', 'model-a', 'call_count') == 3


def test_two_models_under_one_feature_do_not_collide(usage):
    """Whatever the shape, two models sharing the `chat` prefix must keep separate counters."""
    import database.llm_usage as usage_db

    usage_db.record_llm_usage(usage['uid'], 'chat', 'model-a', input_tokens=5, output_tokens=1)
    usage_db.record_llm_usage(usage['uid'], 'chat', 'model-b', input_tokens=7, output_tokens=2)

    daily = usage_db.get_daily_usage(usage['uid'])

    assert _counter(daily, 'chat', 'model-a', 'input_tokens') == 5
    assert _counter(daily, 'chat', 'model-b', 'input_tokens') == 7


def test_a_model_name_with_dots_stays_one_counter(usage):
    """`qwen2.5:14b` contains the path separator. The module sanitizes it to `qwen2_5:14b` before
    building the key; if that ever stopped, the counter would land one level deeper on the backend that
    nests, and become unreadable."""
    import database.llm_usage as usage_db

    usage_db.record_llm_usage(usage['uid'], 'chat', 'qwen2.5:14b', input_tokens=11, output_tokens=3)

    daily = usage_db.get_daily_usage(usage['uid'])

    assert _counter(daily, 'chat', 'qwen2_5:14b', 'input_tokens') == 11
    assert _counter(daily, 'chat', 'qwen2', '5:14b', 'input_tokens') == 0, 'the dot must not split'


def test_the_backends_now_agree_on_both_counts(usage):
    """MEASURED DIVERGENCE (BACKLOG L50), pinned so neither side can drift without telling us. This
    suite found two independent upstream defects on the Firestore path. **One of them is now closed**,
    and this test is the record of that — it was
    `test_the_two_backends_disagree_and_this_pins_both_reasons` while both were open.

    1. CLOSED. `set(..., merge=True)` with a dotted key: real Firestore does not treat a dot as a path
       in `set` — only `update()` does — so it stored one field literally named
       `chat.model-a.input_tokens`, and `_aggregate_summary`, which walks `feature -> model -> ...`,
       skipped it. Our Mongo facade nested, so only the Firestore reader was blind. Upstream took the
       fix (#12065) and now expands the dotted paths before writing, so **both backends nest and the
       divergence is gone**. That is what the first assertion below is for: it fails the day the
       expansion is dropped.
    2. ALSO CLOSED, and this test is how we found out. `get_usage_summary` filtered
       `where("__name__", ">=", cutoff_id)` with a STRING. Firestore requires a Key there and rejected
       the query outright (`400 __key__ filter value must be a Key`), so the reader raised on EVERY
       call; on Mongo the facade maps `__name__` onto the document-name keyset, so a string was fine
       and the defect was invisible there. We proposed the fix upstream as #12066 and the docstring
       said "pinned here until it lands" — it landed in the +135 alignment, Firestore stopped raising,
       and this test failed with DID NOT RAISE. That is the pin doing its job, not a regression.

       Both reasons are now converged, so the assertions below are symmetric: the same shape and the
       same summary on both backends. If either side drifts again, one of them fails.
    """
    import database.llm_usage as usage_db

    usage_db.record_llm_usage(usage['uid'], 'chat', 'model-a', input_tokens=9, output_tokens=1)
    daily = usage_db.get_daily_usage(usage['uid'])

    # Reason 1, now converged: identical shape on both backends.
    assert daily['chat']['model-a']['input_tokens'] == 9
    assert 'chat.model-a.input_tokens' not in daily, 'no literal dotted key survives on either backend'

    # Reason 2, now converged: the summary reader answers on BOTH backends, with the same number.
    assert usage_db.get_usage_summary(usage['uid'], days=1)['chat']['input_tokens'] == 9


# --- transaction ----------------------------------------------------------------------------------


def test_the_same_quota_question_counts_once(usage):
    """Quota. The transaction writes an idempotency event and increments in one commit; a retry must see
    the event and decline. If the read did not see the earlier write, a user would be charged twice for
    one question."""
    import database.llm_usage as usage_db

    key = f"idem-{usage['run']}"
    first = usage_db.record_chat_quota_question(usage['uid'], key, 'mobile')
    second = usage_db.record_chat_quota_question(usage['uid'], key, 'mobile')

    usage['written'].append(
        f"users/{usage['uid']}/chat_quota_events/"
        + __import__('hashlib').sha256(f"{usage['uid']}:{key}".encode()).hexdigest()
    )

    assert first is True, 'the first question must be recorded'
    assert second is False, 'a retry must be declined, not counted again'
    assert _counter(usage_db.get_daily_usage(usage['uid']), 'backend_chat', 'quota_questions') == 1


def test_two_different_questions_both_count(usage):
    """The other direction, so the test above cannot pass by never counting anything."""
    import hashlib

    import database.llm_usage as usage_db

    for suffix in ('a', 'b'):
        key = f"idem-{usage['run']}-{suffix}"
        assert usage_db.record_chat_quota_question(usage['uid'], key, 'mobile') is True
        usage['written'].append(
            f"users/{usage['uid']}/chat_quota_events/" + hashlib.sha256(f"{usage['uid']}:{key}".encode()).hexdigest()
        )

    assert _counter(usage_db.get_daily_usage(usage['uid']), 'backend_chat', 'quota_questions') == 2


# --- collection group with a range filter ---------------------------------------------------------


def test_the_global_sweep_crosses_users_with_a_range_filter(bind_store):
    """`date >= cutoff` over every user's llm_usage subcollection. Distinct from the finalization sweep,
    which filters on equality — a backend can support one and mistranslate the other."""
    import database.llm_usage as usage_db

    run = uuid.uuid4().hex[:8]
    uids = [f'glob{i}-{run}' for i in range(3)]
    feature = f'feat-{run}'
    for uid in uids:
        bind_store.set(
            f'users/{uid}/llm_usage/{TODAY}',
            {'date': TODAY, feature: {'m': {'input_tokens': 10, 'output_tokens': 5, 'call_count': 1}}},
        )
    # Old enough to be outside the window: it must NOT contribute.
    bind_store.set(
        f'users/old-{run}/llm_usage/1999-01-01',
        {'date': '1999-01-01', feature: {'m': {'input_tokens': 999, 'output_tokens': 0, 'call_count': 1}}},
    )

    try:
        top = usage_db.get_global_top_features(days=30, limit=20)
        totals = {entry['feature']: entry for entry in top}

        assert feature in totals, 'the cross-user sweep found none of the three users'
        assert totals[feature]['input_tokens'] == 30, 'three users x 10 tokens, and the old row excluded'
    finally:
        for uid in uids:
            bind_store.delete(f'users/{uid}/llm_usage/{TODAY}')
        bind_store.delete(f'users/old-{run}/llm_usage/1999-01-01')
