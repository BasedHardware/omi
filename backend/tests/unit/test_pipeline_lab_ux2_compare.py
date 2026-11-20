"""Pipeline lab, inspector round 2: change classification, pairing groups and the digest (baseline/compare.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from testing.pipeline_lab.baseline.compare import (
    TAGS,
    baseline_view,
    classify_pair,
    compare_pair,
    edit_size,
    loose_text,
)

T0 = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)


def conv(
    cid,
    minute=0,
    minutes=10,
    *,
    title='Seed swap at the library',
    overview=None,
    emoji='🌱',
    category='other',
    visible=None,
    baseline_id=None,
    baseline_ids=None,
    tasks=(),
    memories=(),
    text='we talked about seeds',
):
    start = T0 + timedelta(minutes=minute)
    row = {
        'id': cid,
        'started_at': start.isoformat(),
        'finished_at': (start + timedelta(minutes=minutes)).isoformat(),
        'discarded': False,
        'segments': [{'start': 0, 'end': 5, 'speaker': 'SPEAKER_0', 'is_user': True, 'text': text}],
        'structured': {
            'title': title,
            'overview': (
                overview if overview is not None else 'You and a neighbour traded tomato seeds and planned a plot.'
            ),
            'emoji': emoji,
            'category': category,
            'events': [],
        },
        'action_items': [{'key': d, 'description': d} for d in tasks],
        'memories': [{'key': m, 'content': m} for m in memories],
        'notifications': [],
        'baseline_id': baseline_id,
    }
    if baseline_ids is not None:
        row['baseline_ids'] = baseline_ids
    if visible is not None:
        row['v3'] = {
            'visible': visible,
            'home_hidden_reason': None if visible else 'below_word_minimum',
            'kind': 'conversation',
        }
    return row


def test_emoji_only_is_cosmetic():
    out = compare_pair(conv('a', emoji='🎙️'), conv('a', emoji='🧪'))
    assert out['status'] == 'cosmetic'
    assert out['substantive_fields'] == [] and out['cosmetic_fields'] == ['emoji']
    assert out['diff']['emoji'] == {'replay': '🎙️', 'production': '🧪'}


def test_category_only_is_cosmetic():
    assert compare_pair(conv('a', category='work'), conv('a'))['status'] == 'cosmetic'


def test_whitespace_case_and_punctuation_only_are_cosmetic():
    replay = conv(
        'a', title='seed swap   at the library!', overview='You and a neighbour traded tomato seeds, and planned a plot'
    )
    fields = classify_pair(replay, conv('a'))
    assert {name: f['class'] for name, f in fields.items()} == {'title': 'cosmetic', 'overview': 'cosmetic'}
    assert compare_pair(replay, conv('a'))['status'] == 'cosmetic'


def test_inner_punctuation_does_not_collide_digits():
    assert loose_text('3.5 kg') != loose_text('35 kg')


def test_rewritten_overview_is_substantive_with_an_edit_size():
    replay = conv('a', overview='The farmers market moved indoors because of the storm warning.')
    out = compare_pair(replay, conv('a'))
    assert out['status'] == 'changed' and out['substantive_fields'] == ['overview']
    found = out['fields']['overview']
    assert found['what'] == 'rewritten' and found['edit_ratio'] >= 0.5 and found['words_changed'] > 5


def test_small_overview_edit_is_edited_not_rewritten():
    replay = conv('a', overview='You and a neighbour traded pepper seeds and planned a plot.')
    found = compare_pair(replay, conv('a'))['fields']['overview']
    assert found['what'] == 'edited' and found['words_changed'] == 1
    assert edit_size('a b c d', 'a b x d')['words_changed'] == 1


def test_task_reworded_added_and_removed_are_counted():
    replay = conv('a', tasks=['Buy fennel seeds for Sunday', 'Call the mill'])
    production = conv('a', tasks=['Buy fennel seeds for the Sunday stew', 'Water plants'])
    found = compare_pair(replay, production)['fields']['tasks']
    assert (found['added'], found['removed'], found['edited']) == (1, 1, 1)


def test_home_flip_is_substantive_and_tagged():
    view = baseline_view([conv('r', visible=False, baseline_id='p')], [conv('p', visible=True)])
    (group,) = view['groups']
    assert group['kind'] == 'content' and 'home_dropped' in group['tags'] and 'worth' in group['tags']
    assert group['change'].startswith('dropped off Home')
    assert view['digest']['home'] == {'production': 1, 'replay': 0}


def _view():
    production = [
        conv('p-same', 0),
        conv('p-emoji', 20),
        conv('p-m1', 40, 5),
        conv('p-m2', 46, 5),
        conv('p-split', 60, 20),
        conv('p-gone', 120, 5, visible=True),
    ]
    replay = [
        conv('r-same', 0, baseline_id='p-same'),
        conv('r-emoji', 20, emoji='🎙️', baseline_id='p-emoji'),
        conv('r-merge', 40, 11, baseline_id='p-m1', baseline_ids=['p-m1', 'p-m2']),
        conv('r-s1', 60, 9, baseline_id='p-split', baseline_ids=['p-split']),
        conv('r-s2', 70, 10, baseline_ids=['p-split']),
        conv('r-new', 200, 5, visible=True),
    ]
    return baseline_view(replay, production)


def test_groups_render_merges_splits_new_and_missing_as_one_unit_each():
    view = _view()
    shapes = {(tuple(g['production']), tuple(g['replay'])): g['kind'] for g in view['groups']}
    assert shapes == {
        (('p-same',), ('r-same',)): 'same',
        (('p-emoji',), ('r-emoji',)): 'cosmetic',
        (('p-m1', 'p-m2'), ('r-merge',)): 'merge',
        (('p-split',), ('r-s1', 'r-s2')): 'split',
        (('p-gone',), ()): 'missing',
        ((), ('r-new',)): 'new',
    }
    markers = {g['kind']: g['marker'] for g in view['groups']}
    assert markers == {'same': '=', 'cosmetic': '~', 'merge': '⇉', 'split': '⇇', 'missing': '−', 'new': '+'}
    merge = next(g for g in view['groups'] if g['kind'] == 'merge')
    assert merge['change'].startswith('2 → 1 merged')
    cosmetic = next(g for g in view['groups'] if g['kind'] == 'cosmetic')
    assert cosmetic['change'] == 'emoji only' and 'worth' not in cosmetic['tags']


def test_digest_counts_are_counts_of_tagged_groups():
    view = _view()
    for tag in TAGS:
        assert view['digest']['tags'][tag] == sum(tag in g['tags'] for g in view['groups']), tag
    assert view['digest']['tags']['worth'] == 4  # merge, split, missing, new; not same or cosmetic
    assert sum(view['digest']['kinds'].values()) == view['digest']['groups'] == len(view['groups'])
    assert view['digest']['conversations'] == {'production': 6, 'replay': 6}
    # every pair row points at its group
    assert all(row['group'] for row in view['conversations'])


def test_weak_shared_recording_link_does_not_chain_groups():
    # r-a overlaps p-b by 1 minute of p-b's 30: not its best link and under half the shorter one.
    production = [conv('p-a', 0, 10), conv('p-b', 9, 30)]
    replay = [
        conv('r-a', 0, 10, baseline_id='p-a', baseline_ids=['p-a', 'p-b']),
        conv('r-b', 10, 29, baseline_id='p-b', baseline_ids=['p-b']),
    ]
    shapes = sorted((tuple(g['production']), tuple(g['replay'])) for g in baseline_view(replay, production)['groups'])
    assert shapes == [(('p-a',), ('r-a',)), (('p-b',), ('r-b',))]


def test_sort_score_puts_home_flip_above_grouping_above_content():
    home = baseline_view([conv('r', visible=False, baseline_id='p')], [conv('p', visible=True)])['groups'][0]
    content = baseline_view([conv('r', overview='Totally different words here now', baseline_id='p')], [conv('p')])[
        'groups'
    ][0]
    grouping = next(g for g in _view()['groups'] if g['kind'] == 'merge')
    cosmetic = next(g for g in _view()['groups'] if g['kind'] == 'cosmetic')
    assert home['score'] > grouping['score'] > content['score'] > cosmetic['score'] > 0


def test_worth_a_look_is_what_the_owner_can_see():
    from testing.pipeline_lab.baseline.compare import _tags

    hidden = {'production': 0, 'replay': 0}
    on_home = {'production': 1, 'replay': 1}
    rewritten = {'overview': {'class': 'substantive'}}
    assert 'worth' not in _tags('split', {}, hidden)  # regrouping that stays hidden
    assert 'worth' not in _tags('content', rewritten, hidden)  # rewrite nobody sees on Home
    assert 'worth' in _tags('content', {'tasks': {'class': 'substantive'}}, hidden)  # tasks surface anyway
    assert 'worth' in _tags('split', {}, on_home)
    assert 'worth' in _tags('content', rewritten, on_home)
    assert 'worth' in _tags('content', {}, {'production': 1, 'replay': 0})  # dropped off Home
