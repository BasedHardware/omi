from routers.desktop_prompts import prompt_matches_audience, rollout_bucket, spec_from_doc


def _doc(**overrides):
    base = {
        'id': 'rate-2026-09',
        'type': 'stars',
        'question': 'How would you rate Omi Desktop?',
        'active': True,
        'trigger': {'kind': 'question_count', 'count': 3},
        'audience': {'rollout_pct': 100},
    }
    base.update(overrides)
    return base


def test_spec_carries_trigger_and_defaults():
    spec = spec_from_doc(_doc())
    assert spec is not None
    assert spec.trigger_kind == 'question_count'
    assert spec.trigger_count == 3
    assert spec.max_per_day == 1
    assert spec.options == []


def test_spec_rejects_unknown_type_and_missing_question():
    assert spec_from_doc(_doc(type='modal')) is None
    assert spec_from_doc(_doc(question=None)) is None
    assert spec_from_doc(_doc(id=None)) is None


def test_banner_spec_carries_cta():
    spec = spec_from_doc(_doc(type='banner', cta={'label': 'Try it', 'url': 'https://omi.me/x'}))
    assert spec is not None
    assert spec.cta_label == 'Try it'
    assert spec.cta_url == 'https://omi.me/x'


def test_channel_audience_excludes_other_channels():
    doc = _doc(audience={'channels': ['beta']})
    assert prompt_matches_audience(doc, 'uid-1', 'beta', 12218)
    assert not prompt_matches_audience(doc, 'uid-1', 'stable', 12218)


def test_min_build_excludes_older_builds_but_not_unknown():
    doc = _doc(audience={'min_build': 12218})
    assert prompt_matches_audience(doc, 'uid-1', 'stable', 12300)
    assert not prompt_matches_audience(doc, 'uid-1', 'stable', 12100)
    # A client that does not report its build is not silently excluded.
    assert prompt_matches_audience(doc, 'uid-1', 'stable', 0)


def test_rollout_bucket_is_stable_and_prompt_scoped():
    a = rollout_bucket('uid-1', 'prompt-a')
    assert a == rollout_bucket('uid-1', 'prompt-a')
    assert 0 <= a < 100
    # Different prompts re-bucket the same user independently.
    buckets = {rollout_bucket('uid-1', f'prompt-{i}') for i in range(20)}
    assert len(buckets) > 1


def test_rollout_pct_gates_by_stable_bucket():
    doc = _doc(audience={'rollout_pct': 0})
    assert not prompt_matches_audience(doc, 'uid-1', 'stable', 0)
    doc = _doc(audience={'rollout_pct': 100})
    assert prompt_matches_audience(doc, 'uid-1', 'stable', 0)
