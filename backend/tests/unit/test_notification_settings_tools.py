import unittest
from unittest.mock import patch

from utils.retrieval.tools.notification_settings_tools import (
    _format_hour,
    manage_daily_summary_tool,
)
import utils.retrieval.tools.notification_settings_tools as notification_settings_tools


class TestNotificationSettingsTools(unittest.TestCase):

    def test_format_hour(self):
        self.assertEqual(_format_hour(0), "12:00 AM (midnight)")
        self.assertEqual(_format_hour(12), "12:00 PM (noon)")
        self.assertEqual(_format_hour(9), "9:00 AM")
        self.assertEqual(_format_hour(22), "10:00 PM")
        self.assertEqual(_format_hour("15"), "3:00 PM")

    def test_invalid_action(self):
        config = {'configurable': {'user_id': 'u1'}}
        res_none = manage_daily_summary_tool.func(action=None, config=config)
        self.assertIn("Action must be a valid non-empty string", res_none)

        res_empty = manage_daily_summary_tool.invoke({'action': '   '}, config=config)
        self.assertIn("Action must be a valid non-empty string", res_empty)

        res_unknown = manage_daily_summary_tool.invoke({'action': 'fly_to_moon'}, config=config)
        self.assertIn("Unknown action: fly_to_moon", res_unknown)

    def test_missing_config_or_user_id(self):
        res_no_cfg = manage_daily_summary_tool.func(action='enable', config=None)
        self.assertIn("Configuration not available", res_no_cfg)

        res_no_uid = manage_daily_summary_tool.func(action='enable', config={})
        self.assertIn("User ID not found", res_no_uid)

        res_empty_conf = manage_daily_summary_tool.invoke({'action': 'enable'}, config={'configurable': {}})
        self.assertIn("User ID not found", res_empty_conf)

    @patch.object(notification_settings_tools, 'notification_db')
    def test_top_level_user_id(self, mock_db):
        mock_db.get_daily_summary_hour_local.return_value = 20
        res = manage_daily_summary_tool.func(action='enable', config={'user_id': 'u_direct'})
        self.assertIn("Daily summary notifications enabled", res)
        mock_db.set_daily_summary_enabled.assert_called_with('u_direct', True)

    @patch.object(notification_settings_tools, 'notification_db')
    def test_action_enable(self, mock_db):
        mock_db.get_daily_summary_hour_local.return_value = 21
        res = manage_daily_summary_tool.invoke({'action': 'enable'}, config={'configurable': {'user_id': 'u1'}})
        self.assertIn("Daily summary notifications enabled", res)
        self.assertIn("9:00 PM", res)
        mock_db.set_daily_summary_enabled.assert_called_with('u1', True)

    @patch.object(notification_settings_tools, 'notification_db')
    def test_action_disable(self, mock_db):
        res = manage_daily_summary_tool.invoke({'action': 'disable'}, config={'configurable': {'user_id': 'u1'}})
        self.assertIn("Daily summary notifications disabled", res)
        mock_db.set_daily_summary_enabled.assert_called_with('u1', False)

    @patch.object(notification_settings_tools, 'notification_db')
    def test_set_time_valid(self, mock_db):
        mock_db.get_daily_summary_enabled.return_value = True
        res = manage_daily_summary_tool.invoke({
            'action': 'set_time',
            'hour': 8,
        }, config={'configurable': {'user_id': 'u1'}})
        self.assertIn("Daily summary time changed to 8:00 AM", res)
        mock_db.set_daily_summary_hour_local.assert_called_with('u1', 8)

    @patch.object(notification_settings_tools, 'notification_db')
    def test_set_time_string_coercion(self, mock_db):
        mock_db.get_daily_summary_enabled.return_value = True
        res = manage_daily_summary_tool.invoke({
            'action': 'set_time',
            'hour': "22",
        }, config={'configurable': {'user_id': 'u1'}})
        self.assertIn("Daily summary time changed to 10:00 PM", res)
        mock_db.set_daily_summary_hour_local.assert_called_with('u1', 22)

    def test_set_time_out_of_bounds_or_invalid(self):
        config = {'configurable': {'user_id': 'u1'}}
        res_high = manage_daily_summary_tool.invoke({'action': 'set_time', 'hour': 25}, config=config)
        self.assertIn("Hour must be between 0 and 23", res_high)

        res_neg = manage_daily_summary_tool.invoke({'action': 'set_time', 'hour': -1}, config=config)
        self.assertIn("Hour must be between 0 and 23", res_neg)

        res_invalid = manage_daily_summary_tool.func(action='set_time', hour="invalid_hour", config=config)
        self.assertIn("Hour must be an integer between 0 and 23", res_invalid)


if __name__ == "__main__":
    unittest.main()
