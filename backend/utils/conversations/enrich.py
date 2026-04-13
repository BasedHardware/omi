"""Conversation enrichment: speaker names, folder names.

Centralizes the enrichment logic that was previously duplicated in
routers/mcp.py, routers/developer.py, and utils/webhooks.py.
"""

from typing import Dict, List

import database.folders as folders_db
import database.users as users_db


def add_speaker_names(uid: str, conversations: List[Dict]) -> None:
    """Add speaker_name to transcript segments based on person_id mappings.

    Mutates conversation dicts in-place. Works with both single conversations
    (pass as [conv]) and lists.

    Replaces: routers/mcp.py::_add_speaker_names_to_segments,
              routers/developer.py::_add_speaker_names_to_segments,
              utils/webhooks.py::_add_speaker_names_to_payload.
    """
    user_profile = users_db.get_user_profile(uid)
    user_name = user_profile.get('name') or 'User'

    all_person_ids = set()
    for conv in conversations:
        for seg in conv.get('transcript_segments', []):
            if seg.get('person_id'):
                all_person_ids.add(seg['person_id'])

    people_map = {}
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
        people_map = {p['id']: p['name'] for p in people_data}

    for conv in conversations:
        for seg in conv.get('transcript_segments', []):
            if seg.get('is_user'):
                seg['speaker_name'] = user_name
            elif seg.get('person_id') and seg['person_id'] in people_map:
                seg['speaker_name'] = people_map[seg['person_id']]
            else:
                seg['speaker_name'] = f"Speaker {seg.get('speaker_id', 0)}"


def add_folder_names(uid: str, conversations: List[Dict]) -> None:
    """Add folder_name to conversations based on folder_id mappings.

    Mutates conversation dicts in-place. Batch-loads all folder IDs in one query.

    Replaces: routers/developer.py::_add_folder_names_to_conversations,
              utils/webhooks.py::_add_folder_name_to_payload.
    """
    folder_ids = set()
    for conv in conversations:
        if conv.get('folder_id'):
            folder_ids.add(conv['folder_id'])

    if not folder_ids:
        for conv in conversations:
            conv['folder_name'] = None
        return

    all_folders = folders_db.get_folders(uid)
    folder_map = {f['id']: f['name'] for f in all_folders}

    for conv in conversations:
        folder_id = conv.get('folder_id')
        conv['folder_name'] = folder_map.get(folder_id) if folder_id else None
