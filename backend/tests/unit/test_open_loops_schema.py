"""Open-loop extraction schema: parsing, back-compat and scrubbing.

Old model outputs without the fields must parse identically; one malformed
entry must never cost the rest of the note (the contract every other
extraction list on these schemas already follows).
"""

from models.structured import Structured
from models.structured_extraction import (
    OpenLoopAgentNotesSubmission,
    OpenLoopStructuredExtraction,
    StructuredExtraction,
)
from utils.llm.notes_output import NotesOutput, OpenLoopNotesOutput
from utils.open_loops.extraction import capture_into_sink, extraction_payload

_NOTE = {
    'title': 'Vendor sync',
    'overview': 'Maya will send the write-up.',
    'emoji': '📝',
    'category': 'work',
    'sections': [],
    'action_items': [],
    'events': [],
}

_DELEGATED = [
    {
        'who': 'Maya',
        'what': 'send the vendor write-up',
        'by_when': None,
        'evidence': '"I will send it over tomorrow"',
        'work_related': True,
    }
]
_ISSUE = {
    'kind': 'work_defect',
    'what': 'File the login-screen crash bug',
    'by_when': None,
    'evidence': 'crash shown during the call',
    'work_related': True,
}


def test_old_outputs_without_the_fields_still_parse():
    for schema in (StructuredExtraction, OpenLoopStructuredExtraction, NotesOutput, OpenLoopNotesOutput):
        parsed = schema.model_validate(_NOTE)
        assert parsed.title == 'Vendor sync'


def test_full_open_loop_payload_parses_on_every_arm():
    payload = {
        **_NOTE,
        'delegated_by_user': _DELEGATED,
        'commitments_by_others': [
            {
                'who': 'the coding agent',
                'what': 'fix the failing test',
                'by_when': 'Monday',
                'evidence': 'asked to fix it',
            }
        ],
        'observed_issue_or_blocker': _ISSUE,
    }
    parsed = OpenLoopStructuredExtraction.model_validate(payload)
    assert parsed.delegated_by_user[0].who == 'Maya'
    assert parsed.commitments_by_others[0].by_when == 'Monday'
    assert parsed.observed_issue_or_blocker.kind == 'work_defect'

    v2 = OpenLoopNotesOutput.model_validate(payload)
    assert v2.delegated_by_user == parsed.delegated_by_user
    agent = OpenLoopAgentNotesSubmission.model_validate(payload)
    assert agent.observed_issue_or_blocker.what == 'File the login-screen crash bug'


def test_one_unusable_entry_does_not_cost_the_note():
    payload = {
        **_NOTE,
        'delegated_by_user': [dict(_DELEGATED[0]), {'who': 'X'}, 'nonsense'],
        'commitments_by_others': None,
    }
    parsed = OpenLoopStructuredExtraction.model_validate(payload)
    assert parsed.title == 'Vendor sync'
    assert [item.who for item in parsed.delegated_by_user] == ['Maya']
    assert parsed.commitments_by_others == []


def test_a_non_list_open_loop_field_never_costs_the_note():
    # A lone object is wrapped; a word or number is dropped. Either way the note survives.
    for model in (OpenLoopStructuredExtraction, OpenLoopNotesOutput, OpenLoopAgentNotesSubmission):
        parsed = model.model_validate(
            {**_NOTE, 'delegated_by_user': dict(_DELEGATED[0]), 'commitments_by_others': 'none'}
        )
        assert [item.who for item in parsed.delegated_by_user] == ['Maya']
        assert parsed.commitments_by_others == []


def test_out_of_vocabulary_issue_kind_becomes_null_not_a_failure():
    payload = {**_NOTE, 'observed_issue_or_blocker': {'kind': 'vibe', 'what': 'something'}}
    parsed = OpenLoopStructuredExtraction.model_validate(payload)
    assert parsed.observed_issue_or_blocker is None
    assert parsed.title == 'Vendor sync'


def test_to_structured_keeps_the_client_wire_unchanged():
    payload = {**_NOTE, 'delegated_by_user': _DELEGATED, 'observed_issue_or_blocker': _ISSUE}
    structured = OpenLoopStructuredExtraction.model_validate(payload).to_structured()
    assert isinstance(structured, Structured)
    dumped = structured.model_dump()
    assert 'delegated_by_user' not in dumped
    assert 'observed_issue_or_blocker' not in dumped


def test_extraction_payload_shape_and_empty_result():
    parsed = OpenLoopStructuredExtraction.model_validate(
        {**_NOTE, 'delegated_by_user': _DELEGATED, 'observed_issue_or_blocker': _ISSUE}
    )
    payload = extraction_payload(parsed)
    assert payload['version'] == 1
    assert payload['delegated_by_user'][0]['who'] == 'Maya'
    assert payload['observed_issue_or_blocker']['kind'] == 'work_defect'

    empty = OpenLoopStructuredExtraction.model_validate(_NOTE)
    assert extraction_payload(empty) is None


def test_capture_into_sink_records_empty_parse_and_ignores_flag_off_schemas():
    sink: dict = {}
    capture_into_sink(OpenLoopStructuredExtraction.model_validate(_NOTE), sink)
    # A fresh parse that found nothing records None: the pipeline persists an
    # explicit clearing null rather than leaving a stale prior value.
    assert sink == {'extractions': None}

    flag_off = NotesOutput.model_validate(_NOTE)
    untouched: dict = {}
    capture_into_sink(flag_off, untouched)
    assert untouched == {}
    capture_into_sink(flag_off, None)  # no sink, no error
