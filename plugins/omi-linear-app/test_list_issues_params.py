"""Hermetic regression tests for plugins/omi-linear-app/main.py list tools.

Standard library only: requests, dotenv, fastapi, db, and models are replaced
with minimal stubs before loading the module under test so the suite runs
under plain python3 (the manifest lane).

Covers #13920: tool_list_my_issues and tool_list_recent_issues interpolated
`limit` and `team` straight into GraphQL text (`first: {limit}`,
`eq: "{team}"`), so null/string/over-cap limits produced malformed queries
and a team key containing quotes or braces could inject arbitrary GraphQL.
Both tools must now pass $first/$filter as variables and run every limit
through coerce_limit().
"""
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
    spec = importlib.util.spec_from_file_location('linear_params_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


ISSUE_NODE = dict(id='issue-id', identifier='ENG-1', title='Fixture issue', priority=2,
                  state=dict(name='Todo', type='unstarted'), assignee=dict(name='Ada'),
                  url='https://linear.app/example', createdAt='2024-01-01', updatedAt='2024-01-02')


class ListIssuesParamsTests(unittest.TestCase):
    defaults = {'tool_list_my_issues': 10, 'tool_list_recent_issues': 5}

    def run_handler(self, name, payload):
        module = load_app()
        calls = []

        def graphql(uid, query, variables=None):
            calls.append((query, variables))
            return {'issues': {'nodes': [ISSUE_NODE]}}

        module.linear_graphql_request = graphql
        module.get_linear_tokens = lambda uid: {'access_token': 'token'}
        body = dict(uid='fixture-user')
        body.update(payload)

        async def json():
            return body

        response = asyncio.run(getattr(module, name)(SimpleNamespace(json=json)))
        return response, calls, module

    def test_coerce_limit_bounds_and_fallbacks(self):
        module = load_app()
        # Defaults for absent/null/non-numeric input
        self.assertEqual(module.coerce_limit(None, default=10), 10)
        self.assertEqual(module.coerce_limit('bogus', default=10), 10)
        self.assertEqual(module.coerce_limit([1], default=10), 10)
        self.assertEqual(module.coerce_limit({'x': 1}, default=10), 10)
        self.assertEqual(module.coerce_limit(float('inf'), default=10), 10)
        self.assertEqual(module.coerce_limit(float('nan'), default=10), 10)
        # String-to-int coercion
        self.assertEqual(module.coerce_limit('15', default=10), 15)
        # Min/max clamping
        self.assertEqual(module.coerce_limit(-10, min_val=1, max_val=50), 1)
        self.assertEqual(module.coerce_limit(0, min_val=1, max_val=50), 1)
        self.assertEqual(module.coerce_limit(999, min_val=1, max_val=50), 50)
        self.assertEqual(module.coerce_limit('1000', min_val=1, max_val=50), 50)

    def test_limits_arrive_as_bounded_int_variables(self):
        for name, default in self.defaults.items():
            cases = [
                ('absent', {}, default),
                ('null', {'limit': None}, default),
                ('string', {'limit': '7'}, 7),
                ('over-cap', {'limit': 999}, 50),
                ('negative', {'limit': -4}, 1),
                ('injection-shaped', {'limit': '5 } } { x'}, default),
            ]
            for label, extra, expected in cases:
                with self.subTest(handler=name, limit=label):
                    response, calls, _ = self.run_handler(name, extra)
                    self.assertIsNone(response.error)
                    self.assertEqual(len(calls), 1)
                    query, variables = calls[0]
                    self.assertIsInstance(variables, dict)
                    self.assertIsInstance(variables['first'], int)
                    self.assertEqual(variables['first'], expected)
                    # The limit is bound through a variable, never interpolated:
                    # `first:` may only appear as the `$first:` declaration or
                    # as the `first: $first` argument, never a literal value.
                    self.assertRegex(query, r'first:\s*\$first\b')
                    self.assertIsNone(re.search(r'(?<!\$)first:\s*[^\s$]', query))

    def test_caller_input_never_interpolates_into_query_text(self):
        # A team key carrying GraphQL metacharacters must stay inert data.
        payload = {'team': 'o" } } { viewer { id } #', 'limit': '25'}
        response, calls, _ = self.run_handler('tool_list_recent_issues', payload)
        self.assertIsNone(response.error)
        query, variables = calls[0]
        self.assertNotIn('viewer', query)
        self.assertNotIn('"', query.replace('$first: Int!', '').replace('$filter: IssueFilter', ''))
        self.assertEqual(variables['first'], 25)
        self.assertEqual(variables['filter'], {'team': {'key': {'eq': 'O" } } { VIEWER { ID } #'}}})
        # The unfiltered variant must not send a filter at all.
        response, calls, _ = self.run_handler('tool_list_recent_issues', {})
        self.assertIsNone(response.error)
        query, variables = calls[0]
        self.assertNotIn('filter', query)
        self.assertEqual(variables, {'first': 5})
        # list_my_issues always filters on the viewer but only ever adds
        # whitelisted state-type constants, never raw status text.
        response, calls, _ = self.run_handler('tool_list_my_issues', {'status': 'done" } } { x'})
        self.assertIsNone(response.error)
        query, variables = calls[0]
        self.assertNotIn('done"', query)
        self.assertEqual(variables['filter'], {'assignee': {'isMe': {'eq': True}}})

    def test_status_and_team_normalization(self):
        # Mapped status merges a structured state filter.
        response, calls, _ = self.run_handler('tool_list_my_issues', {'status': 'In Progress', 'limit': 3})
        self.assertIsNone(response.error)
        _, variables = calls[0]
        self.assertEqual(variables['filter'], {
            'assignee': {'isMe': {'eq': True}},
            'state': {'type': {'eq': 'started'}},
        })
        # Non-string status must not crash the filter builder.
        response, calls, _ = self.run_handler('tool_list_my_issues', {'status': 5})
        self.assertIsNone(response.error)
        _, variables = calls[0]
        self.assertEqual(variables['filter'], {'assignee': {'isMe': {'eq': True}}})
        # Team keys are trimmed and uppercased before becoming filter data.
        response, calls, _ = self.run_handler('tool_list_recent_issues', {'team': '  omi  '})
        self.assertIsNone(response.error)
        _, variables = calls[0]
        self.assertEqual(variables['filter'], {'team': {'key': {'eq': 'OMI'}}})
        self.assertIn('in OMI', response.result)
        # A blank team key selects the unfiltered query and prints no label.
        response, calls, _ = self.run_handler('tool_list_recent_issues', {'team': '   '})
        self.assertIsNone(response.error)
        _, variables = calls[0]
        self.assertEqual(variables, {'first': 5})
        self.assertNotIn('in  ', response.result)


if __name__ == '__main__':
    unittest.main()
