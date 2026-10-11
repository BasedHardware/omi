"""Onboarding PATCHes merge only submitted fields, including explicit false/empty values."""

from copy import deepcopy
from unittest.mock import MagicMock

from database import users


class FieldMergeDocument:
    def __init__(self):
        self.state = {'onboarding': {'completed': False, 'acquisition_source': '', 'future_field': 'keep'}}

    def set(self, data, *, merge):
        # Model Firestore's explicit field mask, not a permissive whole-map update.
        for path in merge:
            parent, field = path.split('.')
            self.state.setdefault(parent, {})[field] = deepcopy(data[parent][field])


def test_disjoint_onboarding_updates_preserve_each_other():
    document = FieldMergeDocument()
    client = MagicMock()
    client.collection.return_value.document.return_value = document
    users.set_user_onboarding_state('owner', {'completed': True}, firestore_client=client)
    users.set_user_onboarding_state('owner', {'acquisition_source': 'Friend'}, firestore_client=client)
    users.set_user_onboarding_state('owner', {'device_onboarding_completed': True}, firestore_client=client)
    assert document.state['onboarding'] == {
        'completed': True,
        'acquisition_source': 'Friend',
        'device_onboarding_completed': True,
        'future_field': 'keep',
    }


def test_explicit_false_and_empty_source_are_written_with_a_field_mask():
    client = MagicMock()
    users.set_user_onboarding_state('owner', {'completed': False, 'acquisition_source': ''}, firestore_client=client)
    client.collection.return_value.document.return_value.set.assert_called_once_with(
        {'onboarding': {'completed': False, 'acquisition_source': ''}},
        merge=['onboarding.completed', 'onboarding.acquisition_source'],
    )


def test_empty_patch_does_not_access_firestore():
    client = MagicMock()
    users.set_user_onboarding_state('owner', {}, firestore_client=client)
    client.collection.assert_not_called()
