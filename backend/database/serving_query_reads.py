"""Shared Firestore read queries for serving endpoints."""

from database._client import get_firestore_client
from dataclasses import dataclass
from copy import deepcopy
from database.fsr_read_cache import serving_config, serving_config_key
from config.firestore_read_levers import lever_enabled


@dataclass
class _S4PromptSnapshot:
    id: str
    data: dict

    def to_dict(self):
        return deepcopy(self.data)


def list_active_desktop_prompt_snapshots(*, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    if lever_enabled('serving_config_cache', serving_config_key()):

        def fetch():
            return [
                _S4PromptSnapshot(doc.id, doc.to_dict() or {})
                for doc in client.collection('desktop_prompts').where('active', '==', True).limit(50).stream()
            ]

        return serving_config('desktop_prompts', fetch, identity=id(client))
    return list(client.collection('desktop_prompts').where('active', '==', True).limit(50).stream())


def list_desktop_release_snapshots(*, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(client.collection('desktop_releases').order_by('build_number', direction='DESCENDING').stream())


def find_fair_use_case_snapshots(case_ref: str, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(client.collection_group('fair_use_events').where('case_ref', '==', case_ref).limit(1).stream())
