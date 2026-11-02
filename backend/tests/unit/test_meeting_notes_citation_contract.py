"""Executable writer/reader contract; expectations are hand-authored across clients."""

import itertools
import json
import re
from pathlib import Path

import pytest

from models.structured import Structured
from utils.llm.meeting_notes_validation import (
    _CODE_RE,
    _repair_note_citation_pass,
    PresentationContractReport,
    enforce_structured_presentation_contract,
    repair_note_citations,
    sanitize_structured_speaker_placeholders,
    visible_text_fields,
)

CONTRACT = json.loads((Path(__file__).resolve().parents[3] / 'contracts/note_citation_contract.json').read_text())
KNOWN = set(CONTRACT['known_ids'])


def assert_visible_invariants(note):
    """Independent assertions: exclude code and real links, then inspect whole groups."""
    for owner, field in visible_text_fields(note):
        text = _CODE_RE.sub('', getattr(owner, field) or '')
        text = re.sub(r'\[[^\]\n]+\]\([^\n)]*\)', '', text)
        for content in re.findall(r'[\[［【]([^\[\]［］【】\n]*)[\]］】]', text):
            content = re.sub('[\u200b\u200c\u200d\u2060\ufeff]', '', content).strip()
            assert re.sub(r'[\s,;]', '', content), (field, text)
            assert not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,95}|\^\d+', content), (field, text)
            tokens = [t for t in re.split(r'[\s,;]+', content) if t]
            assert not any(token in KNOWN for token in tokens), (field, text)
            header = content.split()
            assert not (len(header) == 2 and header[0] in KNOWN and re.fullmatch(r'[?]?[0-9A-Za-z]{1,3}', header[1])), (
                field,
                text,
            )


@pytest.mark.parametrize('case', CONTRACT['cases'], ids=lambda case: case['name'])
def test_render_conformance(case):
    known = set(case.get('known_ids', KNOWN))
    text, ids = repair_note_citations(case['input'], known)
    assert text == case['output']
    assert ids == case['source_ids']
    note = Structured(sections=[{'heading': 'Discussion', 'body_markdown': case['input']}])
    enforce_structured_presentation_contract(note, known, safe_fallback=True)
    assert note.sections[0].body_markdown == case['output']
    assert note.sections[0].source_segment_ids == case['source_ids']
    assert_visible_invariants(note)
    # Every output must be stable across subsequent reads (no delayed shell creation).
    second = note.model_dump()
    enforce_structured_presentation_contract(note, known, safe_fallback=True)
    assert note.model_dump() == second


@pytest.mark.parametrize(
    'strict_input, expected, repairs, violations',
    [
        ('Fact [s01234].', 'Fact.', {'inline_source_citation'}, set()),
        ('Fact [unknown-123].', 'Fact [unknown-123].', set(), {'source_id_in_prose'}),
        ('Fact s01234.', 'Fact s01234.', set(), {'source_id_in_prose'}),
        ('Fact [] [].', 'Fact.', {'empty_citation_dropped'}, set()),
        ('Fact `[unknown-123]`.', 'Fact `[unknown-123]`.', set(), set()),
    ],
)
def test_strict_revision_boundary(strict_input, expected, repairs, violations):
    note = Structured(overview=strict_input)
    report = enforce_structured_presentation_contract(note, KNOWN)
    assert note.overview == expected
    assert report.repairs == repairs
    assert report.violations == violations
    # Only the strict pass may retain a violation while asking for a revision.
    fallback = enforce_structured_presentation_contract(note, KNOWN, safe_fallback=True)
    assert fallback.violations == set()
    assert_visible_invariants(note)


def test_recovery_is_scoped_to_the_owning_object():
    note = Structured(
        title='Title [s01234]',
        overview='Overview [s01235]',
        sections=[
            {
                'heading': 'Heading [s01235]',
                'body_markdown': 'Body [s01234] [s01235]',
                'source_segment_ids': ['s01236', 'invented', 's01236'],
            }
        ],
        action_items=[{'description': 'Do [s01234]', 'context': 'Because [s01235]', 'owner_name': 'Person [s01236]'}],
        participants=[
            {
                'name': 'Name [s01234]',
                'email': 'a@example.com [s01235]',
                'organization': 'Org [s01236]',
                'role': 'Role []',
                'source': 'transcript',
                'evidence': 'Zoom tile [s01234]',
            }
        ],
        insights=[{'text': 'Insight [s01236]', 'kind': 'memory'}],
        events=[{'title': 'Event [s01234]', 'description': 'Event body []', 'start': '2026-01-01T00:00:00Z'}],
    )
    enforce_structured_presentation_contract(note, KNOWN, safe_fallback=True)
    assert note.title == 'Title'
    assert note.overview == 'Overview'
    assert note.sections[0].heading == 'Heading'
    assert note.sections[0].body_markdown == 'Body'
    assert note.sections[0].source_segment_ids == ['s01236', 's01235', 's01234']
    assert note.action_items[0].description == 'Do'
    assert note.action_items[0].context == 'Because'
    assert note.action_items[0].owner_name == 'Person'
    assert note.action_items[0].source_segment_ids == ['s01234', 's01235']
    assert note.participants[0].model_dump() == {
        'name': 'Name',
        'email': 'a@example.com',
        'organization': 'Org',
        'role': 'Role',
        'source': 'transcript',
        'is_ai_agent': False,
        'evidence': 'Zoom tile',
    }
    assert note.insights[0].text == 'Insight'
    assert note.events[0].title == 'Event'
    assert note.events[0].description == 'Event body'
    assert_visible_invariants(note)


@pytest.mark.parametrize('case', CONTRACT['cases'], ids=lambda case: case['name'])
def test_every_visible_field(case):
    known = set(case.get('known_ids', KNOWN))
    note = Structured(
        title=case['input'],
        overview=case['input'],
        sections=[{'heading': case['input'], 'body_markdown': case['input']}],
        action_items=[{'description': case['input'], 'context': case['input'], 'owner_name': case['input']}],
        participants=[
            dict.fromkeys(('name', 'email', 'organization', 'role'), case['input']) | {'source': 'transcript'}
        ],
        insights=[{'text': case['input'], 'kind': 'memory'}],
        events=[{'title': case['input'], 'description': case['input'], 'start': '2026-01-01T00:00:00Z'}],
    )
    enforce_structured_presentation_contract(note, known, safe_fallback=True)
    for owner, field in visible_text_fields(note):
        assert getattr(owner, field) == case['output'], field
    assert note.sections[0].source_segment_ids == case['source_ids']
    assert note.action_items[0].source_segment_ids == case['source_ids']
    assert_visible_invariants(note)


def test_combinatorial_repetition_and_separators():
    # Exhaustive bounded properties, with exact expected strings and provenance.
    for ids in itertools.permutations(sorted(KNOWN)):
        for separator in (' ', ', ', ';', ' ,; '):
            for repeat in (1, 2, 7):
                citation = '[' + separator.join(ids) + ']'
                note = Structured(
                    sections=[{'heading': 'Heading', 'body_markdown': 'Fact. ' + ' '.join([citation] * repeat)}]
                )
                enforce_structured_presentation_contract(note, KNOWN, safe_fallback=True)
                assert note.sections[0].body_markdown == 'Fact.'
                assert note.sections[0].source_segment_ids == list(ids)
                assert_visible_invariants(note)


def test_unknown_drop_is_reported_without_inventing_provenance():
    note = Structured(sections=[{'heading': 'Discussion', 'body_markdown': 'Fact [fabricated-segment].'}])
    strict = enforce_structured_presentation_contract(note, KNOWN)
    assert strict.violations == {'source_id_in_prose'}
    assert note.sections[0].body_markdown == 'Fact [fabricated-segment].'
    fallback = enforce_structured_presentation_contract(note, KNOWN, safe_fallback=True)
    assert fallback.repairs == {'unknown_citation_dropped'}
    assert note.sections[0].body_markdown == 'Fact.'
    assert note.sections[0].source_segment_ids == []
    assert_visible_invariants(note)


def test_early_speaker_sanitizer_also_masks_code():
    code = '`[spk 1] [s01234] []`'
    note = Structured(title=f'spk 1: Use {code}', participants=[{'name': f'Name {code}', 'source': 'transcript'}])
    sanitize_structured_speaker_placeholders(note)
    assert note.title == f'Use {code}'
    assert note.participants[0].name == f'Name {code}'
    assert_visible_invariants(note)


@pytest.mark.parametrize(
    'case', [case for case in CONTRACT['cases'] if 'strict_output' in case], ids=lambda c: c['name']
)
def test_review_strict_and_fallback_contract(case):
    report = PresentationContractReport()
    text, ids = repair_note_citations(case['input'], KNOWN, safe_fallback=False, report=report)
    assert text == case['strict_output']
    assert ids == case['strict_source_ids']
    assert report.violations == set(case['strict_violations'])
    fallback = repair_note_citations(text, KNOWN)
    assert fallback[0] == case['output']
    assert list(dict.fromkeys(ids + fallback[1])) == case['source_ids']


@pytest.mark.parametrize('case', CONTRACT['cases'], ids=lambda c: c['name'])
def test_review_fixed_point_does_not_oscillate(case):
    # Exercise the internal pass independently: convergence cannot be hidden by
    # repair_note_citations' fixed-point loop. Each changing state must be new.
    known = set(case.get('known_ids', KNOWN))
    for fallback in (False, True):
        text = case['input']
        seen = {text}
        for _ in range(len(text) + 1):
            cleaned, _ = _repair_note_citation_pass(text, known, safe_fallback=fallback)
            if cleaned == text:
                break
            assert cleaned not in seen, (case['name'], fallback, seen)
            seen.add(cleaned)
            text = cleaned
        else:
            pytest.fail(f"Repair did not converge: {case['name']}")
        assert repair_note_citations(text, known, safe_fallback=fallback)[0] == text
