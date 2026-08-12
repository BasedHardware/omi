"""send_app_notification must attribute a plugin push via plugin_id.

NotificationMessage has a `plugin_id` field but no `app_id`, and pydantic silently
drops unknown kwargs, so building the message with `app_id=...` left plugin_id at its
None default; get_message_as_dict then deletes the None plugin_id, so the FCM data
payload carried no app attribution at all (the client reads `plugin_id` into the
message's app id). The sibling send_chat_message_notification builds the same message
with plugin_id correctly. These tests guard the caller against regressing to the wrong
key and document why the wrong key drops the attribution.
"""

import models.notification_message as nm
import utils.app_integrations as app_integrations


def test_send_app_notification_attributes_via_plugin_id():
    title, payload = getattr(app_integrations, '_build_app_notification_payload')(
        'Calendar', 'app123', 'Your event starts soon', 'app'
    )

    assert title == 'Calendar says'
    assert payload['plugin_id'] == 'app123'
    assert 'app_id' not in payload


def test_plugin_id_survives_payload_but_unknown_app_id_is_dropped():
    kept = nm.NotificationMessage.get_message_as_dict(
        nm.NotificationMessage(
            text='hi', plugin_id='app123', from_integration='true', type='text', notification_type='plugin'
        )
    )
    assert kept.get('plugin_id') == 'app123'

    # The old wrong key is silently ignored by pydantic, so plugin_id stays None and
    # get_message_as_dict strips it, leaving no app attribution for the client.
    # Note: To simulate the dropping behavior without raising a pyright error on the unexpected argument,
    # we unpack a dictionary containing 'app_id'.
    dropped = nm.NotificationMessage.get_message_as_dict(
        nm.NotificationMessage(
            **{
                'text': 'hi',
                'app_id': 'app123',
                'from_integration': 'true',
                'type': 'text',
                'notification_type': 'plugin',
            }
        )
    )
    assert 'plugin_id' not in dropped
