"""The public /v1/conversations/{id}/shared endpoint must not expose owner-internal fields.

The endpoint returns a conversation to anyone with the link (no auth). It is
meant to publish the transcript/summary the owner shared, not internal fields:
precise geolocation (already stripped), the server-side encryption tier
(`data_protection_level`), or `external_data` (merge provenance — other
conversation ids — and integration metadata).
"""

from types import SimpleNamespace
from unittest.mock import patch

import routers.conversations as conv_router


def test_shared_endpoint_strips_internal_fields_before_serialising():
    conv = SimpleNamespace(
        geolocation='here',
        data_protection_level='enhanced',
        external_data={'merge_metadata': {'source_ids': ['other-conv']}},
    )
    conv.get_person_ids = lambda: []

    captured = {}

    def fake_to_dict(c):
        captured['geolocation'] = c.geolocation
        captured['data_protection_level'] = c.data_protection_level
        captured['external_data'] = c.external_data
        return {'id': 'c1'}

    with patch.object(conv_router.redis_db, 'get_conversation_uid', return_value='owner-uid'), patch.object(
        conv_router, '_get_valid_conversation_by_id', return_value={'visibility': 'public'}
    ), patch.object(conv_router, 'deserialize_conversation', return_value=conv), patch.object(
        conv_router, 'conversation_to_dict', side_effect=fake_to_dict
    ), patch.object(
        conv_router.users_db, 'get_people_by_ids', return_value=[]
    ):
        conv_router.get_shared_conversation_by_id('c1')

    # All three owner-internal fields must be cleared before serialization.
    assert captured['geolocation'] is None
    assert captured['data_protection_level'] is None
    assert captured['external_data'] is None
