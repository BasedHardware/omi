"""Hermetic production-client retries; HTTP/token seams, no credentials or sleeps."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def load_client():
    auth = types.ModuleType('services.auth')
    auth.get_access_token = AsyncMock(return_value='test-only')
    httpx = types.ModuleType('httpx')
    httpx.AsyncClient = lambda **kw: None
    spec = importlib.util.spec_from_file_location('graph_retry_subject', Path(__file__).parent / 'services/graph_client.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'httpx': httpx, 'services.auth': auth}):
        spec.loader.exec_module(module)
    return module


def response(status, header=None):
    return types.SimpleNamespace(status_code=status, headers={} if header is None else {'Retry-After': header},
                                 text='response', content=b'file', json=lambda: {'ok': True})


class GraphRetryTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, method, replies, expected_sleeps, error=None):
        module = load_client()
        client = module.GraphClient('fixture-user')
        request = AsyncMock(side_effect=replies)
        client._client = types.SimpleNamespace(request=request, get=request)
        sleep = AsyncMock()
        with patch.object(module.asyncio, 'sleep', sleep):
            if error:
                with self.assertRaises(module.GraphError) as raised:
                    await getattr(client, method)('/me')
                self.assertEqual(raised.exception.status, error)
            else:
                result = await getattr(client, method)('/me')
                self.assertEqual(result, b'file' if method == 'get_bytes' else {'ok': True})
        self.assertEqual([call.args[0] for call in sleep.await_args_list], expected_sleeps)
        self.assertEqual(request.await_count, len(replies))

    async def test_server_cooldown_then_success(self):
        for method in ('get', 'get_bytes'):
            for status in (429, 503):
                for header, delay in [('60', 60), ('0', 0), (' 7 ', 7),
                                      (str(int(sys.float_info.max)), int(sys.float_info.max))]:
                    with self.subTest(method=method, status=status, header=header):
                        await self.exercise(method, [response(status, header), response(200)], [delay])

    async def test_missing_or_invalid_header_uses_exponential_backoff(self):
        for method in ('get', 'get_bytes'):
            for header in (None, '', 'invalid', '-1', '1.5', '9' * 400, '9' * 5000,
                           str(int(sys.float_info.max) * 2)):
                with self.subTest(method=method, header=header):
                    await self.exercise(method, [response(429, header), response(503, header), response(200)], [2, 3])

    async def test_delay_can_be_scheduled_by_real_event_loop(self):
        module = load_client()
        for header in ('9' * 400, str(int(sys.float_info.max) * 2),
                       str(int(sys.float_info.max)), '60'):
            with self.subTest(header_digits=len(header)):
                # Start the real sleep so call_later performs its float arithmetic,
                # then cancel on the next callback: no timer or wall-clock wait.
                task = asyncio.create_task(asyncio.sleep(module._retry_delay(header, 0)))
                asyncio.get_running_loop().call_soon(task.cancel)
                with self.assertRaises(asyncio.CancelledError):
                    await task

    async def test_attempt_cap_preserves_graph_error(self):
        for method in ('get', 'get_bytes'):
            with self.subTest(method=method):
                await self.exercise(method, [response(429, '60') for _ in range(3)], [60, 60], error=429)

    async def test_non_retryable_error_and_success_do_not_sleep(self):
        for method in ('get', 'get_bytes'):
            for status in (400, 401, 404):
                with self.subTest(method=method, status=status):
                    await self.exercise(method, [response(status)], [], error=status)
            await self.exercise(method, [response(200)], [])


if __name__ == '__main__':
    unittest.main()
