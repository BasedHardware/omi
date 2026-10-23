"""Call-tile names from conferencing OCR, pinned to the shared parity vectors.

The vectors in tests/fixtures/meeting_identity/call_tile_vectors.json are the
contract both extractors implement: this Python one and the macOS
OnDeviceMeetingIdentityService. A change to the rule changes the vectors, and
both sides then have to agree again.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from utils.conversations.meeting_context import (
    call_tile_agent_names,
    call_tile_names,
    context_from_screen_activity,
    strip_leading_tile_glyphs,
)
from utils.conversations.meeting_participants import looks_like_ai_agent_name

VECTORS_PATH = Path(__file__).resolve().parents[1] / 'fixtures' / 'meeting_identity' / 'call_tile_vectors.json'
VECTORS = json.loads(VECTORS_PATH.read_text(encoding='utf-8'))['vectors']
START = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 17, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('vector', VECTORS, ids=[vector['id'] for vector in VECTORS])
def test_tile_names_match_the_shared_vector(vector):
    owners = dict(owner_names=vector['owner_names'], owner_emails=vector['owner_emails'])
    assert call_tile_names(vector['rows'], **owners) == vector['expected_tile_names']
    assert call_tile_agent_names(vector['rows'], **owners) == vector['expected_agent_names']


@pytest.mark.parametrize('vector', VECTORS, ids=[vector['id'] for vector in VECTORS])
def test_extractor_participants_match_the_shared_vector(vector):
    context = context_from_screen_activity(
        vector['rows'],
        started_at=START,
        finished_at=END,
        owner_names=vector['owner_names'],
        owner_emails=vector['owner_emails'],
    )
    everyone = [participant.name for participant in (context.participants if context else []) if participant.name]
    # Agent tiles join as agents (the roster classifies them), never as people.
    names = [name for name in everyone if not looks_like_ai_agent_name(name)]
    assert names == vector['expected_participant_names']
    assert [name for name in everyone if looks_like_ai_agent_name(name)] == vector['expected_agent_names']
    assert not set(names) & set(vector['must_exclude'])
    if context is not None:
        assert context.calendar_source == 'screen_activity'


def test_the_incident_vector_is_present():
    # The rule exists for this incident; losing the vector would un-pin it.
    assert any(vector['id'] == 'meet_1on1_bare_tile_repeated' for vector in VECTORS)


# Zoom's speaking-indicator glyph OCRs glued to the tile name, one variant per
# screenshot ("IllNik Shevchenko", "wIllNik Shevchenko"; conversation 79e8e434:
# notes named no one although every row showed the name). These tests live here,
# not in the shared parity vectors, until the macOS twin strips the glyph too.
def _zoom_call_rows(name_lines, second_tile=None):
    rows = []
    for index, line in enumerate(name_lines):
        lines = [line]
        if second_tile:
            lines.append(second_tile)
        # Zoom control chrome is icon+labeled buttons; lowercase OCR keeps these
        # lines from looking like tile names while still proving a call window.
        lines += ['mute', 'stop video', 'participants', 'share screen', f'09:0{index}']
        rows.append({'appName': 'zoom.us', 'windowTitle': 'Zoom Meeting', 'ocrText': '\n'.join(lines)})
    return rows


def test_speaking_glyph_variants_persist_as_one_tile_name():
    rows = _zoom_call_rows(
        ['IllNik Shevchenko', 'wIllNik Shevchenko', 'IIINik Shevchenko', 'lNik Shevchenko', 'Nik Shevchenko']
    )
    assert call_tile_names(rows) == ['Nik Shevchenko']
    context = context_from_screen_activity(rows, started_at=START, finished_at=END)
    assert [participant.name for participant in (context.participants if context else [])] == ['Nik Shevchenko']


def test_glyphed_tile_does_not_shadow_the_clean_tile_next_to_it():
    rows = _zoom_call_rows(['IllNik Shevchenko', 'wIllNik Shevchenko', 'Nik Shevchenko'], second_tile='Maria Lopez')
    assert sorted(call_tile_names(rows)) == ['Maria Lopez', 'Nik Shevchenko']


def test_glyph_free_names_survive_the_strip_unchanged():
    rows = _zoom_call_rows(['Illinois Smith', 'Illinois Smith', 'Illinois Smith'])
    assert call_tile_names(rows) == ['Illinois Smith']
    rows = _zoom_call_rows(['William Penn', 'William Penn', 'William Penn'])
    assert call_tile_names(rows) == ['William Penn']


@pytest.mark.parametrize(
    ('line', 'expected'),
    [
        ('IllNik Shevchenko', 'Nik Shevchenko'),
        ('wIllNik Shevchenko', 'Nik Shevchenko'),
        ('IIlNik Shevchenko', 'Nik Shevchenko'),
        ('INik Shevchenko', 'Nik Shevchenko'),
        ('Illinois Smith', 'Illinois Smith'),
        ('William Penn', 'William Penn'),
        ('Will Penn', 'Will Penn'),
        ('wIlliam Penn', 'wIlliam Penn'),
        ('III Nik', 'III Nik'),
        ('IllZoom Meeting', 'Zoom Meeting'),
    ],
)
def test_strip_leading_tile_glyphs_is_conservative(line, expected):
    assert strip_leading_tile_glyphs(line) == expected
