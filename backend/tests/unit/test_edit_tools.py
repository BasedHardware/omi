import unittest
from unittest.mock import patch

from utils.retrieval.tools.edit_tools import (
    _extract_configurable,
    owner,
    update_conversation,
    rename_person,
    edit_memory,
    delete_memory,
)


class TestEditTools(unittest.TestCase):

    def test_extract_configurable(self):
        self.assertEqual(_extract_configurable(None), {})
        self.assertEqual(_extract_configurable({}), {})
        self.assertEqual(_extract_configurable({'configurable': None}), {})
        self.assertEqual(_extract_configurable({'configurable': {'user_id': 'u1'}}), {'user_id': 'u1'})
        self.assertEqual(_extract_configurable({'configurable': 'not-a-dict'}), {})

    def test_owner_none_config(self):
        with self.assertRaises(PermissionError):
            owner(None)

    def test_owner_none_configurable(self):
        with self.assertRaises(PermissionError):
            owner({'configurable': None})

    def test_owner_missing_user_id(self):
        with self.assertRaises(PermissionError):
            owner({'configurable': {}})

    def test_owner_nested_user_id(self):
        self.assertEqual(owner({'configurable': {'user_id': 'user_nested'}}), 'user_nested')

    def test_update_conversation_none_or_empty_correction(self):
        config = {'configurable': {'user_id': 'test_user'}}
        with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('conv_1', None)):
            res = update_conversation.func(
                conversation_id='conv_1',
                correction=None,
                title='New Title',
                config=config
            )
            self.assertTrue('invalid_correction' in str(res) or 'Provide a confirmed correction' in str(res))

            res_empty = update_conversation.invoke({
                'conversation_id': 'conv_1',
                'correction': '   ',
                'title': 'New Title',
            }, config=config)
            self.assertTrue('invalid_correction' in str(res_empty) or 'Provide a confirmed correction' in str(res_empty))

    def test_update_conversation_invalid_title(self):
        config = {'configurable': {'user_id': 'test_user'}}
        with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('conv_1', None)):
            res = update_conversation.invoke({
                'conversation_id': 'conv_1',
                'correction': 'Fix title',
                'title': '   ',
            }, config=config)
            self.assertTrue('invalid_title' in str(res) or 'Title must contain' in str(res))

    def test_update_conversation_invalid_overview(self):
        config = {'configurable': {'user_id': 'test_user'}}
        with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('conv_1', None)):
            res = update_conversation.invoke({
                'conversation_id': 'conv_1',
                'correction': 'Fix overview',
                'overview': '   ',
            }, config=config)
            self.assertTrue('invalid_overview' in str(res) or 'Overview must contain' in str(res))

    def test_rename_person_invalid_name(self):
        config = {'configurable': {'user_id': 'test_user'}}
        with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('person_1', None)):
            res_none = rename_person.func(
                person_id='person_1',
                name=None,
                config=config
            )
            self.assertTrue('invalid_name' in str(res_none) or 'Provide a non-empty name' in str(res_none))

            res_empty = rename_person.invoke({
                'person_id': 'person_1',
                'name': '   ',
            }, config=config)
            self.assertTrue('invalid_name' in str(res_empty) or 'Provide a non-empty name' in str(res_empty))

    def test_edit_memory_invalid_content(self):
        config = {'configurable': {'user_id': 'test_user'}}
        with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('mem_1', None)):
            res_none = edit_memory.func(
                memory_id='mem_1',
                content=None,
                config=config
            )
            self.assertTrue('invalid_content' in str(res_none) or 'Provide updated memory content' in str(res_none))

            res_empty = edit_memory.invoke({
                'memory_id': 'mem_1',
                'content': '   ',
            }, config=config)
            self.assertTrue('invalid_content' in str(res_empty) or 'Provide updated memory content' in str(res_empty))


if __name__ == "__main__":
    unittest.main()
