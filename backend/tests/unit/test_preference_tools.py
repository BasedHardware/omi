import unittest
from unittest.mock import patch

from utils.retrieval.tools.preference_tools import (
    _get_uid,
    _write_provenance,
    save_user_preference_tool,
)


class TestPreferenceTools(unittest.TestCase):

    def test_get_uid_nested(self):
        self.assertEqual(_get_uid({'configurable': {'user_id': 'u_nested'}}), 'u_nested')

    def test_get_uid_top_level(self):
        self.assertEqual(_get_uid({'user_id': 'u_top'}), 'u_top')

    def test_get_uid_empty_or_none(self):
        self.assertEqual(_get_uid(None), '')
        self.assertEqual(_get_uid({}), '')
        self.assertEqual(_get_uid({'configurable': None}), '')

    def test_write_provenance_safe_none_preference(self):
        prov = _write_provenance('u1', None, {'configurable': {'user_id': 'u1'}})
        self.assertIsNotNone(prov)

    def test_save_user_preference_whitespace_validation(self):
        config = {'configurable': {'user_id': 'u1'}}
        res_empty = save_user_preference_tool.invoke({'preference': '   '}, config=config)
        self.assertEqual(res_empty, "Error: Preference content cannot be empty")

    def test_save_user_preference_none_func_validation(self):
        config = {'configurable': {'user_id': 'u1'}}
        res_none = save_user_preference_tool.func(preference=None, config=config)
        self.assertEqual(res_none, "Error: Preference content cannot be empty")

    def test_save_user_preference_none_replace_memory_id(self):
        config = {'configurable': {'user_id': 'u1'}}
        with patch('utils.retrieval.tools.preference_tools.get_data_plane_firestore_client'), \
             patch('utils.retrieval.tools.preference_tools.search_canonical_memories', return_value=[]), \
             patch('utils.retrieval.tools.preference_tools.ensure_canonical_apply_control_state') as mock_ctrl, \
             patch('utils.retrieval.tools.preference_tools._save_compatibility_preference', return_value='mem_123'), \
             patch('utils.retrieval.tools.preference_tools.record_write', return_value=''):
            mock_ctrl.return_value.writer_mode = 'compatibility'
            res = save_user_preference_tool.invoke({
                'preference': 'Likes dark chocolate',
                'replace_memory_id': None,
            }, config=config)
            self.assertIn("Preference saved (memory_id=mem_123)", res)

    def test_save_user_preference_whitespace_replace_memory_id(self):
        config = {'configurable': {'user_id': 'u1'}}
        with patch('utils.retrieval.tools.preference_tools.get_data_plane_firestore_client'), \
             patch('utils.retrieval.tools.preference_tools.search_canonical_memories', return_value=[]), \
             patch('utils.retrieval.tools.preference_tools.ensure_canonical_apply_control_state') as mock_ctrl, \
             patch('utils.retrieval.tools.preference_tools._save_compatibility_preference', return_value='mem_456'), \
             patch('utils.retrieval.tools.preference_tools.record_write', return_value=''):
            mock_ctrl.return_value.writer_mode = 'compatibility'
            res = save_user_preference_tool.invoke({
                'preference': 'Likes white chocolate',
                'replace_memory_id': '   ',
            }, config=config)
            self.assertIn("Preference saved (memory_id=mem_456)", res)


if __name__ == "__main__":
    unittest.main()
