"""Hermetic production-handler tests; framework/storage/network imports are seams."""
import asyncio
import importlib.util
from pathlib import Path
import re
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


def issue_lookup_identifier(query, variables):
    # Follow the variable bound to issue(id:), not an unrelated variable's value.
    match = re.search(r'\bissue\s*\(\s*id\s*:\s*\$([_A-Za-z][_0-9A-Za-z]*)\s*\)', query)
    if match is None:
        raise AssertionError('Expected an exact issue lookup')
    return variables[match.group(1)]


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
            self.assertEqual(issue_lookup_identifier(query, variables), 'ENG-123')
            return lookup if lookup is not None else {'issue': ISSUE}

        module.linear_graphql_request = graphql
        module.get_linear_tokens = lambda uid: authenticated
        module.find_state_by_name = Mock(return_value=(SimpleNamespace(id='done-id', name='Done'), [SimpleNamespace(id='done-id', name='Done')]))
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
                self.assertEqual(issue_lookup_identifier(*calls[0]), 'ENG-123')
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

    def test_find_state_by_name_precedence(self):
        module = load_app()
        states = [
            SimpleNamespace(id='not-done-id', name='Not Done', type='unstarted'),
            SimpleNamespace(id='shipped-id', name='Shipped', type='completed'),
            SimpleNamespace(id='incomplete-id', name='Incomplete', type='unstarted'),
            SimpleNamespace(id='todo-later-id', name='Todo Later', type='unstarted'),
            SimpleNamespace(id='not-in-prog-id', name='Not In Progress', type='unstarted'),
            SimpleNamespace(id='active-id', name='Active', type='started'),
        ]
        module.get_team_states = Mock(return_value=states)

        # Exact match takes precedence
        state, candidates = module.find_state_by_name('uid', 'team', 'Not Done')
        self.assertEqual(state.id, 'not-done-id')
        self.assertEqual([c.id for c in candidates], ['not-done-id'])

        # Type alias takes precedence over partial match
        # 'done' -> type 'completed' ('Shipped'), NOT substring match in 'Not Done'
        self.assertEqual(module.find_state_by_name('uid', 'team', 'done')[0].id, 'shipped-id')
        self.assertEqual(module.find_state_by_name('uid', 'team', 'complete')[0].id, 'shipped-id')
        self.assertEqual(module.find_state_by_name('uid', 'team', 'in progress')[0].id, 'active-id')

        # Partial match works when no exact or type match
        self.assertEqual(module.find_state_by_name('uid', 'team', 'Later')[0].id, 'todo-later-id')

        # Unknown state returns no state and no candidates
        state, candidates = module.find_state_by_name('uid', 'team', 'Nonexistent Status')
        self.assertIsNone(state)
        self.assertEqual(candidates, [])

    def test_find_state_by_name_ambiguous_partial_match_is_refused(self):
        # Regression: 'find_state_by_name' used to return whichever state
        # happened to be listed first when several names matched. "review"
        # matches both "In Review" and "Peer Review"; silently picking one
        # would move the issue to a status the caller never asked for.
        module = load_app()
        states = [
            SimpleNamespace(id='in-review-id', name='In Review', type='started'),
            SimpleNamespace(id='peer-review-id', name='Peer Review', type='started'),
        ]
        module.get_team_states = Mock(return_value=states)
        state, candidates = module.find_state_by_name('uid', 'team', 'review')
        self.assertIsNone(state)
        self.assertEqual(sorted(c.id for c in candidates), ['in-review-id', 'peer-review-id'])

    def test_find_state_by_name_ambiguous_type_alias_is_refused(self):
        # A Linear team can have more than one state of the same type, e.g.
        # two "started" columns for two stages of in-progress work.
        module = load_app()
        states = [
            SimpleNamespace(id='dev-id', name='In Dev', type='started'),
            SimpleNamespace(id='qa-id', name='In QA', type='started'),
        ]
        module.get_team_states = Mock(return_value=states)
        state, candidates = module.find_state_by_name('uid', 'team', 'in progress')
        self.assertIsNone(state)
        self.assertEqual(sorted(c.id for c in candidates), ['dev-id', 'qa-id'])

    def test_update_issue_status_reports_ambiguous_candidates(self):
        module = load_app()
        states = [
            SimpleNamespace(id='in-review-id', name='In Review', type='started'),
            SimpleNamespace(id='peer-review-id', name='Peer Review', type='started'),
        ]

        def graphql(uid, query, variables=None):
            if 'searchIssues' in query:
                return {'searchIssues': {'nodes': [WRONG]}}
            return {'issue': ISSUE}

        module.linear_graphql_request = graphql
        module.get_linear_tokens = lambda uid: True
        module.get_team_states = Mock(return_value=states)
        payload = dict(uid='fixture-user', issue_identifier='eng-123', new_status='review')

        async def json():
            return payload

        response = asyncio.run(module.tool_update_issue_status(SimpleNamespace(json=json)))
        self.assertIsNotNone(response.error)
        self.assertIn('In Review', response.error)
        self.assertIn('Peer Review', response.error)


if __name__ == '__main__':
    unittest.main()

