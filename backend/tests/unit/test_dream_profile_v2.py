"""Profile v2: ref-grounded lines, pinned identity line, byte-stable render (shadow only)."""

import re

from database import auth
from utils import dream_profile_v2 as profile
from utils.dream_profile_v2 import ProfileLineOp

CORPUS = {'memories/m1', 'memories/m2', 'people/anna', 'conversations/c1', 'action_items/t1'}


def _apply(ops, previous=None, corpus=CORPUS):
    return profile.apply_ops(previous, ops, run_id='run-1', now='2026-10-31', corpus_refs=corpus)


def _render(state, name='David Zhang', corpus=CORPUS):
    return profile.render(state, identity_name=name, corpus_refs=corpus, rendered_at='t', section_digests={})


def test_lines_must_cite_supplied_refs_and_people_lines_need_an_owner_anchor():
    state, counts = _apply(
        [
            ProfileLineOp(op='add', section='work', text='Works on Omi hardware.', refs=['memories/m1']),
            ProfileLineOp(op='add', section='work', text='Unsupported claim.', refs=['memories/nope']),
            ProfileLineOp(op='add', section='people', text='Anna likes tea.', refs=['people/anna']),
            ProfileLineOp(
                op='add', section='people', text='Meets Anna weekly.', refs=['people/anna', 'conversations/c1']
            ),
            ProfileLineOp(op='add', section='work', text='', refs=['memories/m1']),
        ]
    )
    assert counts['add'] == 2 and counts['rejected'] == 3
    texts = [line.text for section in state.sections for line in section.lines]
    assert texts == ['Works on Omi hardware.', 'Meets Anna weekly.']


def test_identity_ops_are_ignored_and_line_one_is_the_user_doc_name():
    state, counts = _apply(
        [ProfileLineOp(op='add', section='identity', text='Anna is the owner.', refs=['memories/m1'])]
    )
    assert counts['identity_ignored'] == 1 and state.sections == []
    rendered, _stale = _render(state)
    assert rendered.profile_text.split('\n')[0] == '- David Zhang'
    # database.auth parses this first line as the owner's name.
    assert auth._profile_name(rendered.profile_text + '\n- Works on Omi.') in {'David Zhang', None}


def test_render_is_deterministic_without_timestamps():
    ops = [
        ProfileLineOp(op='add', section='projects', text='Building a pendant.', refs=['memories/m2']),
        ProfileLineOp(op='add', section='work', text='Works on Omi.', refs=['memories/m1']),
    ]
    first, _ = _render(_apply(ops)[0])
    second, _ = _render(_apply(list(reversed(ops)))[0])
    assert first.profile_text == second.profile_text
    assert not re.search(r'\d{4}-\d{2}-\d{2}', first.profile_text)
    # Fixed section order: work before projects.
    assert first.profile_text.index('Works on Omi.') < first.profile_text.index('Building a pendant.')


def test_stale_refs_are_excluded_from_the_render_and_counted():
    state, _ = _apply([ProfileLineOp(op='add', section='work', text='Works on Omi.', refs=['memories/m1'])])
    rendered, stale = _render(state, corpus={'memories/m2'})
    assert stale == 1 and rendered.profile_text == '- David Zhang'


def test_update_and_drop_need_an_existing_unpinned_line():
    state, _ = _apply([ProfileLineOp(op='add', section='work', text='Works on Omi.', refs=['memories/m1'])])
    line_id = state.sections[0].lines[0].id
    updated, counts = _apply(
        [
            ProfileLineOp(
                op='update', line_id=line_id, section='work', text='Leads Omi hardware.', refs=['memories/m1']
            ),
            ProfileLineOp(op='drop', line_id='missing', section='work'),
        ],
        previous=state,
    )
    assert counts['update'] == 1 and counts['rejected'] == 1
    assert updated.sections[0].lines[0].text == 'Leads Omi hardware.'
    dropped, counts = _apply([ProfileLineOp(op='drop', line_id=line_id, section='work')], previous=updated)
    assert counts['drop'] == 1 and dropped.sections == []


def test_caps_hold():
    ops = [
        ProfileLineOp(op='add', section='work', text=f'Fact number {index}.', refs=['memories/m1'])
        for index in range(20)
    ]
    state, counts = _apply(ops)
    assert len(state.sections[0].lines) == profile.MAX_LINES_PER_SECTION
    assert counts['rejected'] == 20 - profile.MAX_LINES_PER_SECTION


def test_doc_round_trip():
    state, _ = _apply([ProfileLineOp(op='add', section='work', text='Works on Omi.', refs=['memories/m1'])])
    rendered, _ = _render(state)
    doc = profile.to_doc(state, rendered, 'David Zhang')
    assert doc['rendered']['profile_text'] == rendered.profile_text
    restored = profile.from_doc(doc)
    assert restored is not None and restored.sections == state.sections
    assert profile.from_doc({'sections': 'broken'}) is None
    # The exact persisted shape carries side metadata beside the schema fields.
    stored = {**doc, 'notes': 'next week', 'run_started_at': '2026-10-31T00:00:00Z'}
    restored = profile.from_doc(stored)
    assert restored is not None and restored.sections == state.sections
