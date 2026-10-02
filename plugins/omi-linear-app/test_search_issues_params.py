"""Hermetic regression tests for plugins/omi-linear-app/main.py search tool.

Standard library only: requests, dotenv, fastapi, db, and models are replaced
with minimal stubs before loading the module under test so the suite runs
under plain python3 (the manifest lane).

The #13920 coerce-limit pass covered tool_list_my_issues and
tool_list_recent_issues but left tool_search_issues on a raw
`body.get("limit", 5)`. dict.get returns None -- not the default -- when the
key is present and null, which is exactly what the backend sends for an
omitted optional parameter, so `first` reached Linear as null against a
non-nullable `$first: Int!`. Both the primary searchIssues query and the
issues(filter:) fallback bind the same value, so the tool had no recovery
path and every limit-less search failed. tool_search_issues must now run the
caller-supplied limit through coerce_limit() on both query paths.
"""
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
    spec = importlib.util.spec_from_file_location('linear_search_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


ISSUE_NODE = dict(id='issue-id', identifier='ENG-1', title='Fixture issue', priority=2,
                  state=dict(name='Todo'), assignee=dict(name='Ada'),
                  url='https://linear.app/example')

SEARCH_DEFAULT = 5


class SearchIssuesParamsTests(unittest.TestCase):
    def run_search(self, payload, primary_fails=False):
        """Drive tool_search_issues with a stubbed GraphQL transport.

        primary_fails=True makes the searchIssues query return an error so the
        issues(filter:) fallback runs, letting us assert the fallback binds a
        coerced limit too.
        """
        module = load_app()
        calls = []

        def graphql(uid, query, variables=None):
            calls.append((query, variables))
            if 'searchIssues' in query:
                if primary_fails:
                    return {'error': 'primary unavailable'}
                return {'searchIssues': {'nodes': [ISSUE_NODE]}}
            return {'issues': {'nodes': [ISSUE_NODE]}}

        module.linear_graphql_request = graphql
        module.get_linear_tokens = lambda uid: {'access_token': 'token'}
        body = dict(uid='fixture-user', query='fixture search')
        body.update(payload)

        async def json():
            return body

        response = asyncio.run(module.tool_search_issues(SimpleNamespace(json=json)))
        return response, calls

    def test_limit_arrives_as_bounded_int_variable(self):
        cases = [
            ('absent', {}, SEARCH_DEFAULT),
            ('null', {'limit': None}, SEARCH_DEFAULT),
            ('string', {'limit': '7'}, 7),
            ('over-cap', {'limit': 999}, 50),
            ('negative', {'limit': -4}, 1),
            ('zero', {'limit': 0}, 1),
            ('float', {'limit': 3.7}, 3),
            ('bool', {'limit': True}, 1),
            ('list', {'limit': [5]}, SEARCH_DEFAULT),
            ('dict', {'limit': {'n': 5}}, SEARCH_DEFAULT),
            ('injection-shaped', {'limit': '5 } } { x'}, SEARCH_DEFAULT),
        ]
        for label, extra, expected in cases:
            with self.subTest(limit=label):
                response, calls = self.run_search(extra)
                self.assertIsNone(response.error)
                self.assertTrue(calls, 'expected a GraphQL call')
                _query, variables = calls[0]
                self.assertIsInstance(variables, dict)
                self.assertNotIsInstance(variables['first'], bool)
                self.assertIsInstance(variables['first'], int)
                self.assertEqual(variables['first'], expected)

    def test_fallback_query_also_binds_a_coerced_limit(self):
        # A null limit must not poison the issues(filter:) fallback either;
        # both paths declare a non-nullable $first: Int!.
        response, calls = self.run_search({'limit': None}, primary_fails=True)
        self.assertIsNone(response.error)
        self.assertEqual(len(calls), 2, 'expected primary + fallback calls')
        for label, (_query, variables) in zip(('primary', 'fallback'), calls):
            with self.subTest(path=label):
                self.assertIsInstance(variables['first'], int)
                self.assertEqual(variables['first'], SEARCH_DEFAULT)

    def test_search_never_sends_null_first(self):
        # Regression guard for the reported failure: `first` may never be None.
        for extra in ({}, {'limit': None}, {'limit': 'bogus'}):
            with self.subTest(payload=extra):
                _response, calls = self.run_search(extra, primary_fails=True)
                for _query, variables in calls:
                    self.assertIsNotNone(
                        variables.get('first'),
                        'first must never be null against $first: Int!')


if __name__ == '__main__':
    unittest.main()
