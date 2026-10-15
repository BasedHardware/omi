"""Hermetic unit tests for malformed Person doc resilience in search_conversations_text."""

import types
from unittest.mock import patch
from tests.unit.test_tools_router import (
    conversations_db,
    conversations_svc,
    render_mod,
    users_db,
    vector_db,
)


class TestSearchConversationsTextMalformedPerson:
    def setup_method(self):
        vector_db.query_vectors.reset_mock()
        vector_db.query_vectors.return_value = []
        conversations_db.get_conversations_by_id.reset_mock()
        conversations_db.get_conversations_by_id.return_value = []
        users_db.get_people_by_ids.reset_mock()
        users_db.get_people_by_ids.return_value = []
        render_mod.conversations_to_string.reset_mock()

    def test_malformed_person_is_skipped_not_error(self):
        """A legacy person doc missing the required name must be skipped in search, not error out.

        Before the fix, Person(**p) raised out of the unguarded people list-comp in search_conversations_text,
        causing the function to catch Exception and return an error message string instead of formatted results.
        Now the bad person is skipped (and logged) and the search still returns with the good speaker resolved.
        """
        vector_db.query_vectors.return_value = ['conv-1']
        conversations_db.get_conversations_by_id.return_value = [
            {'id': 'conv-1', 'transcript_segments': [{'person_id': 'p-good'}, {'person_id': 'p-bad'}], 'title': 'T'},
        ]
        users_db.get_people_by_ids.return_value = [
            {'id': 'p-good', 'name': 'Alice'},
            {'id': 'p-bad'},  # legacy doc missing the required 'name'
        ]

        def fake_person(**kwargs):
            if 'name' not in kwargs:
                raise ValueError("Person requires name")  # stand-in for pydantic ValidationError
            return types.SimpleNamespace(**kwargs)

        with patch.object(conversations_svc, 'Person', side_effect=fake_person):
            result = conversations_svc.search_conversations_text(
                uid="test-uid", query="test query", include_transcript=True
            )

        assert "Error" not in result
        assert "Found 1 conversations" in result
        people_arg = render_mod.conversations_to_string.call_args.kwargs['people']
        assert [pp.name for pp in people_arg] == ['Alice']  # malformed person skipped, good one kept
