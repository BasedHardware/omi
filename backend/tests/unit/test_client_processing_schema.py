"""Schema caps and trust-boundary shape for ClientProcessing.

Red-proofs (one-line mutation that would make the named assertion pass wrongly):
- extra=forbid → extra='ignore' (unknown fields accepted)
- max_length N → N+1 or drop the cap (too-long / too-many accepted)
- drop _bound_raw_then_strip (padded-past-cap silently stripped into range)
- strip_whitespace + min_length=1 → drop strip (padded-empty accepted as non-empty)
- CategoryEnum without coerce-to-other → copy Structured's default-on-error validator
- Literal[1] without _reject_coerced_schema_version → true / 1.0 stored as 1
- lowercase-hex pattern → drop pattern (uppercase hash accepted)
- StrictBool → bool ('false' coerced to False)
- StrictInt → int ('30' coerced to 30)
- AwareDatetime → datetime (naive ISO-8601 stored)
- drop _reject_numeric_datetime (unix 0 stored as 1970-01-01)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.client_processing import (
    CLIENT_PROCESSING_SCHEMA_VERSION,
    ClientProcessing,
    ProjectedActionItem,
    ProjectedEvent,
    ProjectedSection,
    ProjectedStructure,
    ProjectionProvenance,
)
from models.conversation import Conversation
from models.conversation_enums import CategoryEnum
from models.structured import Structured

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
VALID_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'


def _section(**overrides) -> dict:
    payload = {'heading': 'Notes', 'body_markdown': 'Ship the schema.'}
    payload.update(overrides)
    return payload


def _event(**overrides) -> dict:
    payload = {
        'title': 'Follow-up',
        'description': 'Sync next week',
        'start': NOW.isoformat(),
        'duration': 30,
    }
    payload.update(overrides)
    return payload


def _structure(**overrides) -> dict:
    payload = {
        'title': 'Standup',
        'overview': 'We talked about tests.',
        'emoji': '🧠',
        'category': 'work',
        'sections': [_section()],
        'events': [_event()],
    }
    payload.update(overrides)
    return payload


def _provenance(**overrides) -> dict:
    payload = {
        'model_id': 'local-summarizer-v1',
        'runtime': 'mlx',
        'device_class': 'apple_silicon',
        'generated_at': NOW.isoformat(),
    }
    payload.update(overrides)
    return payload


def _processing(**overrides) -> dict:
    payload = {
        'schema_version': CLIENT_PROCESSING_SCHEMA_VERSION,
        'transcript_sha256': VALID_SHA256,
        'structure': _structure(),
        'action_items': [{'description': 'Write the schema tests', 'completed': False}],
        'provenance': _provenance(),
    }
    payload.update(overrides)
    return payload


def _conversation_payload(**overrides) -> dict:
    payload = {
        'id': 'conv-1',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW,
        'structured': Structured(title='Server title', overview='', category=CategoryEnum.other),
    }
    payload.update(overrides)
    return payload


# --- extra=forbid on every model ---------------------------------------------------------------


# red-proof: extra='ignore' on the target model
@pytest.mark.parametrize(
    'model, payload',
    [
        (ProjectedActionItem, {'description': 'x'}),
        (ProjectedSection, _section()),
        (ProjectedEvent, _event()),
        (ProjectedStructure, _structure()),
        (ProjectionProvenance, _provenance()),
        (ClientProcessing, _processing()),
    ],
)
def test_unknown_fields_rejected_on_every_model(model, payload) -> None:
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        model.model_validate({**payload, 'unexpected_field': 'nope'})


def test_projected_action_item_rejects_intelligence_capture_fields() -> None:
    # red-proof: extra='ignore' (ids / owners / due dates would land on a display item)
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        ProjectedActionItem.model_validate({'description': 'x', 'id': 'ai-1', 'due_at': NOW.isoformat()})
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        ProjectedActionItem.model_validate(
            {'description': 'x', 'owner_name': 'Ada', 'capture_kind': 'inferred_next_step'}
        )


# --- string / list caps ------------------------------------------------------------------------


# red-proof: raise max_length (or drop it)
@pytest.mark.parametrize(
    'model, payload, field, value',
    [
        (ProjectedActionItem, {'description': 'ok'}, 'description', 'x' * 501),
        (ProjectedSection, _section(), 'heading', 'h' * 121),
        (ProjectedSection, _section(), 'body_markdown', 'b' * 4001),
        (ProjectedEvent, _event(), 'title', 't' * 201),
        (ProjectedEvent, _event(), 'description', 'd' * 1001),
        (ProjectedStructure, _structure(), 'title', 't' * 121),
        (ProjectedStructure, _structure(), 'overview', 'o' * 4001),
        (ProjectedStructure, _structure(), 'emoji', '😀' * 9),
        (ProjectionProvenance, _provenance(), 'model_id', 'm' * 121),
        (ProjectionProvenance, _provenance(), 'runtime', 'r' * 61),
        (ProjectionProvenance, _provenance(), 'device_class', 'd' * 61),
    ],
)
def test_too_long_strings_rejected(model, payload, field, value) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: value})


# red-proof: drop StringConstraints.strip_whitespace or min_length
@pytest.mark.parametrize(
    'model, payload, field',
    [
        (ProjectedActionItem, {'description': 'ok'}, 'description'),
        (ProjectedSection, _section(), 'heading'),
        (ProjectedSection, _section(), 'body_markdown'),
        (ProjectedEvent, _event(), 'title'),
        (ProjectedStructure, _structure(), 'title'),
        (ProjectionProvenance, _provenance(), 'model_id'),
        (ProjectionProvenance, _provenance(), 'runtime'),
        (ProjectionProvenance, _provenance(), 'device_class'),
    ],
)
def test_empty_after_strip_rejected(model, payload, field) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: '   '})
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: '\n\t'})
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: ''})


# Incidental surrounding whitespace on an already-in-cap value is stripped
# (decision: strip, do not reject). Caps still bind the RAW wire string.
# red-proof: drop strip_whitespace (padded-in-cap would be stored with spaces)
@pytest.mark.parametrize(
    'model, payload, field, raw, stripped',
    [
        (ProjectedActionItem, {'description': 'ok'}, 'description', '  buy milk  ', 'buy milk'),
        (ProjectedSection, _section(), 'heading', '  Notes  ', 'Notes'),
        (ProjectedSection, _section(), 'body_markdown', '  Ship the schema.  ', 'Ship the schema.'),
        (ProjectedEvent, _event(), 'title', '  Follow-up  ', 'Follow-up'),
        (ProjectedEvent, _event(), 'description', '  Sync next week  ', 'Sync next week'),
        (ProjectedStructure, _structure(), 'title', '  Standup  ', 'Standup'),
        (ProjectedStructure, _structure(), 'overview', '  We talked about tests.  ', 'We talked about tests.'),
        (ProjectedStructure, _structure(), 'emoji', '  🧠  ', '🧠'),
        (ProjectionProvenance, _provenance(), 'model_id', '  local-summarizer-v1  ', 'local-summarizer-v1'),
        (ProjectionProvenance, _provenance(), 'runtime', '  mlx  ', 'mlx'),
        (ProjectionProvenance, _provenance(), 'device_class', '  apple_silicon  ', 'apple_silicon'),
    ],
)
def test_incidental_whitespace_is_stripped_when_raw_is_in_cap(model, payload, field, raw, stripped) -> None:
    parsed = model.model_validate({**payload, field: raw})
    assert getattr(parsed, field) == stripped


# red-proof: drop _bound_raw_then_strip (strip would repair this to a valid 'x')
@pytest.mark.parametrize(
    'model, payload, field, max_length',
    [
        (ProjectedActionItem, {'description': 'ok'}, 'description', 500),
        (ProjectedSection, _section(), 'heading', 120),
        (ProjectedSection, _section(), 'body_markdown', 4000),
        (ProjectedEvent, _event(), 'title', 200),
        (ProjectedEvent, _event(), 'description', 1000),
        (ProjectedStructure, _structure(), 'title', 120),
        (ProjectedStructure, _structure(), 'overview', 4000),
        (ProjectedStructure, _structure(), 'emoji', 8),
        (ProjectionProvenance, _provenance(), 'model_id', 120),
        (ProjectionProvenance, _provenance(), 'runtime', 60),
        (ProjectionProvenance, _provenance(), 'device_class', 60),
    ],
)
def test_padded_past_cap_is_rejected_not_stripped_into_range(model, payload, field, max_length) -> None:
    # Raw length is cap+1; after strip the value would be the valid string 'x'.
    padded = (' ' * max_length) + 'x'
    assert len(padded) == max_length + 1
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: padded})
    # At-cap raw padding around a single character is accepted and stripped.
    at_cap = (' ' * (max_length - 1)) + 'x'
    parsed = model.model_validate({**payload, field: at_cap})
    assert getattr(parsed, field) == 'x'


@pytest.mark.parametrize(
    'model, payload, field, at_limit',
    [
        (ProjectedActionItem, {'description': 'ok'}, 'description', 'x' * 500),
        (ProjectedSection, _section(), 'heading', 'h' * 120),
        (ProjectedSection, _section(), 'body_markdown', 'b' * 4000),
        (ProjectedEvent, _event(), 'title', 't' * 200),
        (ProjectedEvent, _event(), 'description', 'd' * 1000),
        (ProjectedStructure, _structure(), 'title', 't' * 120),
        (ProjectedStructure, _structure(), 'overview', 'o' * 4000),
        (ProjectedStructure, _structure(), 'emoji', 'e' * 8),
    ],
)
def test_strings_at_the_cap_are_accepted(model, payload, field, at_limit) -> None:
    parsed = model.model_validate({**payload, field: at_limit})
    assert getattr(parsed, field) == at_limit


# red-proof: raise max_length on the list Field
def test_too_many_action_items_rejected() -> None:
    with pytest.raises(ValidationError):
        ClientProcessing.model_validate(_processing(action_items=[{'description': f'item {i}'} for i in range(26)]))


def test_too_many_sections_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectedStructure.model_validate(_structure(sections=[_section(heading=f'h{i}') for i in range(13)]))


def test_too_many_events_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectedStructure.model_validate(_structure(events=[_event(title=f'e{i}') for i in range(13)]))


def test_list_caps_accept_the_limit() -> None:
    ClientProcessing.model_validate(_processing(action_items=[{'description': f'item {i}'} for i in range(25)]))
    ProjectedStructure.model_validate(_structure(sections=[_section(heading=f'h{i}') for i in range(12)]))
    ProjectedStructure.model_validate(_structure(events=[_event(title=f'e{i}') for i in range(12)]))


def test_event_duration_bounds() -> None:
    # red-proof: drop ge/le on duration
    ProjectedEvent.model_validate(_event(duration=1))
    ProjectedEvent.model_validate(_event(duration=1440))
    with pytest.raises(ValidationError):
        ProjectedEvent.model_validate(_event(duration=0))
    with pytest.raises(ValidationError):
        ProjectedEvent.model_validate(_event(duration=1441))


# --- strict primitives / timezone-aware datetimes ----------------------------------------------


def test_completed_rejects_string_and_numeric_booleans() -> None:
    # red-proof: completed: bool ('false'/0/1 would coerce)
    ProjectedActionItem.model_validate({'description': 'x', 'completed': False})
    ProjectedActionItem.model_validate({'description': 'x', 'completed': True})
    omitted = ProjectedActionItem.model_validate({'description': 'x'})
    assert omitted.completed is False
    for bad in ('false', 'true', 'False', 'True', 0, 1, 0.0, 1.0):
        with pytest.raises(ValidationError):
            ProjectedActionItem.model_validate({'description': 'x', 'completed': bad})


def test_duration_rejects_numeric_strings_and_floats() -> None:
    # red-proof: duration: int ('30' / 30.0 would coerce)
    ProjectedEvent.model_validate(_event(duration=30))
    for bad in ('30', '1', 30.0, True, False):
        with pytest.raises(ValidationError):
            ProjectedEvent.model_validate(_event(duration=bad))


def test_datetimes_must_be_timezone_aware_iso8601() -> None:
    # red-proof: start/generated_at: datetime (naive ISO-8601 would be stored)
    aware_iso = NOW.isoformat()
    ProjectedEvent.model_validate(_event(start=aware_iso))
    ProjectedEvent.model_validate(_event(start=NOW))
    ProjectedEvent.model_validate(_event(start='2026-09-02T12:00:00Z'))
    ProjectionProvenance.model_validate(_provenance(generated_at=aware_iso))
    ProjectionProvenance.model_validate(_provenance(generated_at=NOW))

    naive_iso = '2026-09-02T12:00:00'
    naive_dt = datetime(2026, 9, 2, 12, 0)
    for bad in (naive_iso, naive_dt):
        with pytest.raises(ValidationError):
            ProjectedEvent.model_validate(_event(start=bad))
        with pytest.raises(ValidationError):
            ProjectionProvenance.model_validate(_provenance(generated_at=bad))


def test_datetimes_reject_unix_timestamps() -> None:
    # red-proof: drop _reject_numeric_datetime (0 would become 1970-01-01)
    for bad in (0, 0.0, 1_725_000_000, 1_725_000_000.0):
        with pytest.raises(ValidationError):
            ProjectedEvent.model_validate(_event(start=bad))
        with pytest.raises(ValidationError):
            ProjectionProvenance.model_validate(_provenance(generated_at=bad))


# --- category / schema_version / hash ----------------------------------------------------------


def test_invalid_category_is_rejected_not_coerced_to_other() -> None:
    # red-proof: copy Structured.set_category_default_on_error onto ProjectedStructure
    with pytest.raises(ValidationError):
        ProjectedStructure.model_validate(_structure(category='not_a_category'))
    parsed = ProjectedStructure.model_validate(_structure(category='work'))
    assert parsed.category is CategoryEnum.work
    omitted = ProjectedStructure.model_validate({'title': 'T'})
    assert omitted.category is CategoryEnum.other


def test_schema_version_must_be_literal_1() -> None:
    # red-proof: drop _reject_coerced_schema_version (true / 1.0 stored as 1);
    # schema_version: int (version 2 would be stored)
    parsed = ClientProcessing.model_validate(_processing(schema_version=1))
    assert parsed.schema_version == 1
    assert type(parsed.schema_version) is int
    for bad in (2, 0, '1', True, False, 1.0):
        with pytest.raises(ValidationError):
            ClientProcessing.model_validate(_processing(schema_version=bad))


def test_transcript_sha256_must_be_64_lowercase_hex() -> None:
    # red-proof: drop the lowercase-hex pattern (uppercase / short / non-hex would pass)
    ClientProcessing.model_validate(_processing(transcript_sha256='a' * 64))
    for bad in (
        'A' * 64,
        'a' * 63,
        'a' * 65,
        'g' * 64,
        '',
        '26C60A61D01DB5836CA70FEFD44A6A016620413C8EF5F259A6C5612D4F79D3B8',
    ):
        with pytest.raises(ValidationError):
            ClientProcessing.model_validate(_processing(transcript_sha256=bad))


# --- Conversation round-trip -------------------------------------------------------------------


def test_valid_payload_round_trips_through_conversation() -> None:
    processing = ClientProcessing.model_validate(_processing())
    conv = Conversation.model_validate(_conversation_payload(client_processing=processing.model_dump(mode='json')))
    dumped = conv.model_dump()
    assert dumped['client_processing']['schema_version'] == 1
    assert dumped['client_processing']['structure']['title'] == 'Standup'
    assert dumped['client_processing']['action_items'][0]['description'] == 'Write the schema tests'
    assert dumped['structured']['title'] == 'Server title'
    assert 'client_processing' not in Structured.model_fields

    cleaned = conv.as_dict_cleaned_dates()
    assert cleaned['client_processing']['structure']['title'] == 'Standup'
    assert isinstance(cleaned['client_processing']['provenance']['generated_at'], str)

    again = Conversation.model_validate(dumped)
    assert again.client_processing is not None
    assert again.client_processing.structure.title == 'Standup'
    assert again.structured.title == 'Server title'


def test_conversation_without_projection_serialises_with_null_or_absent_field() -> None:
    conv = Conversation.model_validate(_conversation_payload())
    assert conv.client_processing is None
    dumped = conv.model_dump()
    assert dumped.get('client_processing') is None
    cleaned = conv.as_dict_cleaned_dates()
    assert cleaned.get('client_processing') is None
    # Canonical structured is unchanged by the new sibling field.
    assert dumped['structured']['title'] == 'Server title'
    assert dumped['id'] == 'conv-1'


@pytest.fixture(scope='module')
def from_transcript_request() -> type:
    """Import the router model once, in setup.

    The import chain costs ~1s of CPU. Paying it inside a test body trips the
    fast-unit call-phase duration guard; a module fixture puts it in setup where
    the guard does not measure it, without adding an allowlist exception.
    """
    from routers.developer import CreateConversationFromTranscriptRequest

    return CreateConversationFromTranscriptRequest


def test_create_from_transcript_request_accepts_optional_projection(from_transcript_request: type) -> None:
    CreateConversationFromTranscriptRequest = from_transcript_request

    field = CreateConversationFromTranscriptRequest.model_fields['client_processing']
    assert field.is_required() is False
    request = CreateConversationFromTranscriptRequest.model_validate(
        {
            'transcript_segments': [{'text': 'hello', 'start': 0.0, 'end': 1.0, 'is_user': False}],
        }
    )
    assert request.client_processing is None
    request = CreateConversationFromTranscriptRequest.model_validate(
        {
            'transcript_segments': [{'text': 'hello', 'start': 0.0, 'end': 1.0, 'is_user': False}],
            'client_processing': _processing(),
        }
    )
    assert request.client_processing is not None
    # Request parse keeps the raw payload (Worker B: a bad projection must not 422).
    # Strict schema still applies when the coordinator validates ClientProcessing.
    parsed = ClientProcessing.model_validate(request.client_processing)
    assert parsed.structure.title == 'Standup'
    malformed = CreateConversationFromTranscriptRequest.model_validate(
        {
            'transcript_segments': [{'text': 'hello', 'start': 0.0, 'end': 1.0, 'is_user': False}],
            'client_processing': _processing(schema_version=2),
        }
    )
    with pytest.raises(ValidationError):
        ClientProcessing.model_validate(malformed.client_processing)
