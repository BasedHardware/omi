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
        'db': {
            name: Mock(side_effect=AssertionError('Unexpected storage'))
            for name in (
                'store_linear_tokens',
                'get_linear_tokens',
                'delete_linear_tokens',
                'is_token_expired',
                'store_default_team',
                'get_default_team',
                'get_user_settings',
            )
        },
        'models': {
            name: Response if name == 'ChatToolResponse' else SimpleNamespace
            for name in (
                'ChatToolResponse',
                'LinearIssue',
                'LinearTeam',
                'LinearProject',
                'LinearComment',
                'LinearUser',
                'WorkflowState',
            )
        },
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('linear_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


ISSUE = dict(
    id='exact-id',
    identifier='ENG-123',
    title='Exact issue',
    url='https://linear.app/example',
    team=dict(id='team-id', name='Engineering'),
    state=dict(name='Todo'),
    labels=dict(nodes=[]),
)
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


class WorkflowStatePrecedenceTests(unittest.TestCase):
    """Hermetic tests ensuring workflow type aliases take precedence over conflicting partial state names (#13984)."""

    def setUp(self):
        self.module = load_app()
        self.trap_states = [
            self.module.WorkflowState(id='not-done-id', name='Not Done', type='unstarted', color='#888', position=0),
            self.module.WorkflowState(id='shipped-id', name='Shipped', type='completed', color='#888', position=1),
            self.module.WorkflowState(
                id='incomplete-id', name='Incomplete', type='unstarted', color='#888', position=2
            ),
            self.module.WorkflowState(
                id='not-in-progress-id', name='Not In Progress', type='unstarted', color='#888', position=3
            ),
            self.module.WorkflowState(id='working-id', name='Working', type='started', color='#888', position=4),
            self.module.WorkflowState(id='todo-later-id', name='Todo Later', type='backlog', color='#888', position=5),
            self.module.WorkflowState(id='ready-id', name='Ready', type='unstarted', color='#888', position=6),
            self.module.WorkflowState(
                id='code-review-id', name='Code Review', type='started', color='#888', position=7
            ),
            self.module.WorkflowState(id='exact-done-id', name='Done', type='completed', color='#888', position=8),
        ]

    def test_find_state_type_aliases_precede_conflicting_partial_names(self):
        # Without exact 'Done' state, 'done' must resolve to 'Shipped' (completed), not 'Not Done' (unstarted)
        states_without_exact_done = [s for s in self.trap_states if s.name != 'Done']
        self.module.get_team_states = Mock(return_value=states_without_exact_done)

        state = self.module.find_state_by_name('u1', 't1', 'done')
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 'shipped-id')
        self.assertEqual(state.type, 'completed')

        # 'complete' must resolve to 'Shipped' (completed), not 'Incomplete' (unstarted)
        state = self.module.find_state_by_name('u1', 't1', 'complete')
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 'shipped-id')
        self.assertEqual(state.type, 'completed')

        # Issue #13984: input "todo" must resolve to an 'unstarted' state ('not-done-id'), not 'Todo Later' (backlog)
        state = self.module.find_state_by_name('u1', 't1', 'todo')
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 'not-done-id')
        self.assertEqual(state.type, 'unstarted')
        self.assertNotEqual(state.id, 'todo-later-id')

        # 'in progress' must resolve to 'Working' (started), not 'Not In Progress' (unstarted)
        state = self.module.find_state_by_name('u1', 't1', 'in progress')
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 'working-id')
        self.assertEqual(state.type, 'started')

    def test_find_state_exact_match_precedence(self):
        self.module.get_team_states = Mock(return_value=self.trap_states)

        # Exact match for 'Done' returns 'Done'
        state = self.module.find_state_by_name('u1', 't1', 'Done')
        self.assertEqual(state.id, 'exact-done-id')

        # Exact match for 'Not Done' returns 'Not Done'
        state = self.module.find_state_by_name('u1', 't1', 'Not Done')
        self.assertEqual(state.id, 'not-done-id')

    def test_find_state_custom_partial_fallback(self):
        self.module.get_team_states = Mock(return_value=self.trap_states)

        # 'review' is not a standard alias; falls back to partial match on 'Code Review'
        state = self.module.find_state_by_name('u1', 't1', 'review')
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 'code-review-id')

    def test_find_state_unknown_returns_none(self):
        self.module.get_team_states = Mock(return_value=self.trap_states)
        self.assertIsNone(self.module.find_state_by_name('u1', 't1', 'nonexistent_status'))

    def test_tool_update_issue_status_with_real_resolution(self):
        # End-to-end through tool_update_issue_status without mocking find_state_by_name
        states_without_exact_done = [s for s in self.trap_states if s.name != 'Done']
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            if 'team(id: $teamId)' in query:
                return {
                    'team': {
                        'states': {
                            'nodes': [
                                {'id': s.id, 'name': s.name, 'type': s.type, 'color': s.color, 'position': s.position}
                                for s in states_without_exact_done
                            ]
                        }
                    }
                }
            if 'mutation UpdateIssue' in query:
                return {'issueUpdate': {'success': True, 'issue': {'state': {'name': 'Shipped'}}}}
            return {'issue': ISSUE}

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True

        async def json():
            return {'uid': 'fixture-user', 'issue_identifier': 'ENG-123', 'new_status': 'done'}

        response = asyncio.run(self.module.tool_update_issue_status(SimpleNamespace(json=json)))
        self.assertIsNone(response.error)
        self.assertIn('Shipped', response.result)

        # Verify mutation targeted 'shipped-id', NOT 'not-done-id'
        update_calls = [c for c in graphql_calls if 'mutation UpdateIssue' in c[0]]
        self.assertEqual(len(update_calls), 1)
        self.assertEqual(update_calls[0][1]['input']['stateId'], 'shipped-id')

    def test_tool_update_issue_status_unknown_does_not_mutate(self):
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            if 'team(id: $teamId)' in query:
                return {
                    'team': {
                        'states': {
                            'nodes': [
                                {'id': s.id, 'name': s.name, 'type': s.type, 'color': s.color, 'position': s.position}
                                for s in self.trap_states
                            ]
                        }
                    }
                }
            return {'issue': ISSUE}

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True

        async def json():
            return {'uid': 'fixture-user', 'issue_identifier': 'ENG-123', 'new_status': 'invalid_xyz'}

        response = asyncio.run(self.module.tool_update_issue_status(SimpleNamespace(json=json)))
        self.assertIsNotNone(response.error)
        self.assertIn("Could not find status 'invalid_xyz'", response.error)

        # No UpdateIssue mutation executed
        update_calls = [c for c in graphql_calls if 'mutation UpdateIssue' in c[0]]
        self.assertEqual(len(update_calls), 0)


if __name__ == '__main__':
    unittest.main()
