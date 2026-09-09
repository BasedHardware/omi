"""Hermetic production-handler tests; framework/storage/network imports are seams."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class App:
    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def mount(self, *args, **kwargs):
        pass


class Response:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error


def load_app():
    modules = {}
    definitions = {
        'fastapi': dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock()),
        'fastapi.responses': dict(HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        'fastapi.staticfiles': dict(StaticFiles=Mock()),
        'fastapi.templating': dict(Jinja2Templates=Mock()),
        'dotenv': dict(load_dotenv=lambda: None),
        'requests': dict(post=Mock(side_effect=AssertionError('Unexpected HTTP')), RequestException=Exception),
        'db': {name: Mock(side_effect=AssertionError('Unexpected storage')) for name in (
            'store_linear_tokens', 'get_linear_tokens', 'delete_linear_tokens', 'is_token_expired',
            'store_default_team', 'get_default_team', 'get_user_settings')},
        'models': {name: Response if name == 'ChatToolResponse' else SimpleNamespace for name in (
            'ChatToolResponse', 'LinearIssue', 'LinearTeam', 'LinearProject', 'LinearComment', 'LinearUser', 'WorkflowState')},
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('linear_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


ISSUE = dict(id='exact-id', identifier='ENG-123', title='Exact issue', url='https://linear.app/example',
             team=dict(id='team-id', name='Engineering'), state=dict(name='Todo'), labels=dict(nodes=[]))
WRONG = dict(ISSUE, id='wrong-id', identifier='ENG-1234', title='Different issue')


class IssueLookupTests(unittest.TestCase):
    handlers = ('tool_get_issue', 'tool_update_issue_status', 'tool_add_comment')

    def run_handler(self, name, lookup=None, body=None, authenticated=True, mutation_error=None):
        module = load_app()
        calls = []

        def graphql(uid, query, variables=None):
            calls.append((query, variables))
            if 'mutation UpdateIssue' in query:
                return mutation_error or {'issueUpdate': {'success': True, 'issue': {'state': {'name': 'Done'}}}}
            if 'mutation CreateComment' in query:
                return mutation_error or {'commentCreate': {'success': True}}
            if 'searchIssues' in query:
                # Faithful full-text response: a related issue can be ranked first.
                return {'searchIssues': {'nodes': [WRONG]}}
            if 'issue(id: $id)' in query and variables == {'id': 'ENG-123'}:
                return lookup if lookup is not None else {'issue': ISSUE}
            raise AssertionError('Unexpected GraphQL lookup contract')

        module.linear_graphql_request = graphql
        module.get_linear_tokens = lambda uid: authenticated
        module.find_state_by_name = Mock(return_value=SimpleNamespace(id='done-id', name='Done'))
        payload = dict(uid='fixture-user', issue_identifier='eng-123', new_status='Done', comment='Test note')
        if body:
            payload.update(body)

        async def json():
            return payload

        response = asyncio.run(getattr(module, name)(SimpleNamespace(json=json)))
        return response, calls, module

    def test_exact_target_and_mutations(self):
        for name in self.handlers:
            with self.subTest(handler=name):
                response, calls, module = self.run_handler(name)
                self.assertIsNone(response.error)
                self.assertIn('ENG-123', response.result)
                self.assertNotIn('ENG-1234', response.result)
                self.assertEqual(calls[0][1], {'id': 'ENG-123'})
                if name == 'tool_update_issue_status':
                    self.assertEqual(calls[1][1], {'id': 'exact-id', 'input': {'stateId': 'done-id'}})
                    module.find_state_by_name.assert_called_once_with('fixture-user', 'team-id', 'Done')
                elif name == 'tool_add_comment':
                    self.assertEqual(calls[1][1], {'input': {'issueId': 'exact-id', 'body': 'Test note'}})
                else:
                    self.assertEqual(len(calls), 1)

    def test_missing_or_inaccessible_never_mutates(self):
        for name in self.handlers:
            for lookup in ({'issue': None}, {}, {'error': 'Access denied'}):
                with self.subTest(handler=name, lookup=lookup):
                    response, calls, module = self.run_handler(name, lookup=lookup)
                    self.assertIsNone(response.result)
                    self.assertIn('Access denied' if 'error' in lookup else 'Could not find issue', response.error)
                    self.assertEqual(len(calls), 1)
                    module.find_state_by_name.assert_not_called()

    def test_validation_and_authentication_make_no_request(self):
        for name in self.handlers:
            for body, authenticated in (({'uid': ''}, True), ({'issue_identifier': ''}, True), ({}, False)):
                with self.subTest(handler=name, body=body, authenticated=authenticated):
                    response, calls, _ = self.run_handler(name, body=body, authenticated=authenticated)
                    self.assertIsNotNone(response.error)
                    self.assertEqual(calls, [])

    def test_mutation_error_propagates(self):
        for name in self.handlers[1:]:
            with self.subTest(handler=name):
                response, calls, _ = self.run_handler(name, mutation_error={'error': 'Mutation denied'})
                self.assertIn('Mutation denied', response.error)
                self.assertEqual(len(calls), 2)

    def test_keyword_search_still_uses_search(self):
        response, calls, _ = self.run_handler('tool_search_issues', body={'query': 'keyword', 'limit': 3})
        self.assertIsNone(response.error)
        self.assertIn('ENG-1234', response.result)
        self.assertEqual(calls[0][1], {'term': 'keyword', 'first': 3})


if __name__ == '__main__':
    unittest.main()
