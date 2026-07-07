"""Shared Firestore invariant helpers used by aggregated ZachL111 fixes."""

import pytest
from pydantic import ValidationError

from database.document_ids import calendar_meeting_doc_id, system_folder_doc_id
from models.folder import ReorderFoldersRequest


def test_system_folder_doc_ids_are_stable_per_uid_and_category():
    first = system_folder_doc_id('uid-1', 'work')
    second = system_folder_doc_id('uid-1', 'work')

    assert first == second
    assert first != system_folder_doc_id('uid-1', 'personal')
    assert first != system_folder_doc_id('uid-2', 'work')


def test_calendar_meeting_doc_ids_include_available_provider_dimensions():
    base = calendar_meeting_doc_id('uid-1', 'google_calendar', 'event-1')

    assert base == calendar_meeting_doc_id('uid-1', 'google_calendar', 'event-1')
    assert base != calendar_meeting_doc_id('uid-1', 'outlook_calendar', 'event-1')
    assert base != calendar_meeting_doc_id('uid-2', 'google_calendar', 'event-1')
    assert base != calendar_meeting_doc_id('uid-1', 'google_calendar', 'event-2')


def test_reorder_folder_request_rejects_duplicate_ids_before_writes():
    with pytest.raises(ValidationError):
        ReorderFoldersRequest(folder_ids=['folder-a', 'folder-a'])

    assert ReorderFoldersRequest(folder_ids=['folder-a', 'folder-b']).folder_ids == ['folder-a', 'folder-b']
