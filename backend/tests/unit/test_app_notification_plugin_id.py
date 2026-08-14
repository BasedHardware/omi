"""Plugin push notifications must attribute the app on the FCM payload.

The Flutter client derives a message's app identity from `app_id` (the
deprecated plugin_id wire key was removed from the parser). NotificationMessage
now carries both plugin_id (legacy) and app_id, and the plugin notification
producers set both so the pushed answer keeps its app attribution on new and
old clients alike.
"""

import models.notification_message as nm
import utils.app_integrations as app_integrations


def test_send_app_notification_attributes_via_plugin_id_and_app_id():
    title, payload = getattr(app_integrations, '_build_app_notification_payload')(
        'Calendar', 'app123', 'Your event starts soon', 'app'
    )

    assert title == 'Calendar says'
    assert payload['plugin_id'] == 'app123'
    assert payload['app_id'] == 'app123'


def test_notification_message_keeps_both_identity_keys():
    kept = nm.NotificationMessage.get_message_as_dict(
        nm.NotificationMessage(
            text='hi',
            plugin_id='app123',
            app_id='app123',
            from_integration='true',
            type='text',
            notification_type='plugin',
        )
    )
    assert kept.get('plugin_id') == 'app123'
    assert kept.get('app_id') == 'app123'


def test_get_message_as_dict_strips_absent_identity_keys():
    stripped = nm.NotificationMessage.get_message_as_dict(
        nm.NotificationMessage(text='hi', from_integration='true', type='text', notification_type='daily_summary')
    )
    assert 'plugin_id' not in stripped
    assert 'app_id' not in stripped
