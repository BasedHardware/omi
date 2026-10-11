"""Execute the production handler and retry helper without service imports.

Only decorators/default dependency bindings are removed from the handler AST;
its body and the retry helper are compiled unchanged, not reimplemented.
Asana wire contract: https://developers.asana.com/docs/pagination
"""

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


def load_function(path, name, namespace):
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    node.decorator_list = []
    node.args.defaults = [] if name == 'get_asana_projects' else [ast.Constant(None)]
    node.returns = None
    for arg in node.args.args:
        arg.annotation = None
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace[name]


class AsanaProjectPaginationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pages = []
        self.calls = []
        self.integration = {'connected': True, 'access_token': 'initial'}
        self.refresh = AsyncMock(return_value={'connected': True, 'access_token': 'renewed'})
        self.ns = {
            'HTTPException': HTTPError,
            'db_executor': None,
            'run_blocking': AsyncMock(return_value=self.integration),
            'users_db': SimpleNamespace(get_task_integration=None),
            'ensure_valid_oauth_token': AsyncMock(return_value=self.integration),
            'get_http_client': lambda: SimpleNamespace(get=self.get),
            'refresh_oauth_token': self.refresh,
            'logger': logging.getLogger(__name__),
        }
        backend = Path(__file__).resolve().parents[2]
        load_function(backend / 'utils/task_integrations_ops.py', 'perform_request_with_token_retry', self.ns)
        self.handler = load_function(backend / 'routers/task_integrations.py', 'get_asana_projects', self.ns)

    async def get(self, url, headers, params=None):
        query = parse_qs(urlsplit(url).query)
        query.update({k: [str(v)] for k, v in (params or {}).items()})
        self.calls.append((urlsplit(url)._replace(query='').geturl(), query, headers.copy()))
        status, body = self.pages.pop(0)
        return SimpleNamespace(status_code=status, json=lambda: body)

    async def test_multiple_pages_keep_filters_and_opaque_cursor(self):
        cursor = 'a+b/=& c'
        self.pages = [
            (200, {'data': [{'gid': '1'}], 'next_page': {'offset': cursor}}),
            (200, {'data': [{'gid': '2'}], 'next_page': None}),
        ]
        result = await self.handler('workspace', 'uid')
        self.assertEqual(result, {'projects': [{'gid': '1'}, {'gid': '2'}]})
        self.assertEqual(len(self.calls), 2)
        for url, query, _ in self.calls:
            self.assertEqual(url, 'https://app.asana.com/api/1.0/projects')
            self.assertEqual(query['workspace'], ['workspace'])
            self.assertEqual(query['archived'], ['false'])
            self.assertEqual(query['opt_fields'], ['name,gid,owner'])
            self.assertEqual(query['limit'], ['100'])
        self.assertNotIn('offset', self.calls[0][1])
        self.assertEqual(self.calls[1][1]['offset'], [cursor])

    async def test_empty_final_page(self):
        self.pages = [(200, {'data': [], 'next_page': None})]
        self.assertEqual(await self.handler('workspace', 'uid'), {'projects': []})
        self.assertEqual(len(self.calls), 1)

    async def test_later_failure_never_returns_partial_success(self):
        self.pages = [(200, {'data': [{'gid': '1'}], 'next_page': {'offset': 'next'}}), (503, {})]
        with self.assertRaises(HTTPError) as error:
            await self.handler('workspace', 'uid')
        self.assertEqual(error.exception.status_code, 503)

    async def test_later_page_token_retry_is_carried_forward(self):
        self.pages = [
            (200, {'data': [], 'next_page': {'offset': 'second'}}),
            (401, {}),
            (200, {'data': [{'gid': '2'}], 'next_page': {'offset': 'third'}}),
            (200, {'data': [{'gid': '3'}], 'next_page': None}),
        ]
        self.assertEqual(await self.handler('workspace', 'uid'), {'projects': [{'gid': '2'}, {'gid': '3'}]})
        self.assertEqual(
            [c[2]['Authorization'] for c in self.calls],
            ['Bearer initial', 'Bearer initial', 'Bearer renewed', 'Bearer renewed'],
        )
        self.assertEqual(self.calls[1][1], self.calls[2][1])
        self.refresh.assert_awaited_once()

    async def test_repeated_cursor_fails_without_looping(self):
        self.pages = [(200, {'data': [], 'next_page': {'offset': 'same'}})] * 2
        with self.assertRaises(HTTPError) as error:
            await self.handler('workspace', 'uid')
        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
