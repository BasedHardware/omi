"""Offline behavioral coverage of the complete production Calendar module.

Framework, persistence and HTTP dependencies are doubles; parser, handlers,
API request construction and event formatting execute production code.
"""
import asyncio
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def load_app():
    modules = {name: ModuleType(name) for name in
               ('requests', 'dotenv', 'fastapi', 'fastapi.responses', 'db', 'models')}
    app = SimpleNamespace(get=lambda *a, **k: lambda f: f,
                          post=lambda *a, **k: lambda f: f)
    modules['fastapi'].FastAPI = lambda **kwargs: app
    modules['fastapi'].Request = object
    modules['fastapi'].Query = lambda value, **kwargs: value
    modules['fastapi'].HTTPException = Exception
    for name in ('HTMLResponse', 'RedirectResponse', 'JSONResponse'):
        setattr(modules['fastapi.responses'], name, Mock())
    modules['dotenv'].load_dotenv = lambda: None
    for name in ('store_google_tokens', 'get_google_tokens', 'update_google_tokens',
                 'delete_google_tokens', 'store_oauth_state', 'get_oauth_state',
                 'delete_oauth_state', 'store_user_setting', 'get_user_setting'):
        setattr(modules['db'], name, Mock(return_value=None))
    modules['db'].get_google_tokens.return_value = {'access_token': 'offline-fixture'}
    modules['models'].ChatToolResponse = lambda **kwargs: SimpleNamespace(**kwargs)
    for method in ('get', 'post', 'patch'):
        setattr(modules['requests'], method, Mock())
    spec = importlib.util.spec_from_file_location('calendar_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict('sys.modules', modules):
        spec.loader.exec_module(module)
    module.log = lambda message: None
    return module


class Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


class CalendarDatetimeTests(unittest.TestCase):
    def setUp(self):
        self.app = load_app()
        response = SimpleNamespace(status_code=200, json=lambda: {'id': 'fixture-event'})
        for method in ('get', 'post', 'patch'):
            getattr(self.app.requests, method).return_value = response

    def call(self, mode, **fields):
        body = dict(uid='fixture-user', event_id='fixture-event', title='Fixture')
        body.update(fields)
        result = asyncio.run(getattr(self.app, 'tool_' + mode + '_event')(Request(body)))
        return result, getattr(self.app.requests, 'post' if mode == 'create' else 'patch')

    def assert_instant(self, wire, expected):
        # Google interprets naive dateTime using the supplied timeZone (UTC).
        actual = datetime.fromisoformat(wire['dateTime'])
        if actual.tzinfo is None:
            self.assertEqual(wire['timeZone'], 'UTC')
            actual = actual.replace(tzinfo=timezone.utc)
        self.assertEqual(actual.astimezone(timezone.utc), expected)

    def test_explicit_start_and_end_preserve_instants(self):
        for mode in ('create', 'update'):
            for suffix, hour, minute in (('+05:30', 8, 30), ('-04:00', 18, 0), ('Z', 14, 0)):
                for fraction in ('.123', ''):
                    with self.subTest(mode=mode, suffix=suffix, fraction=fraction):
                        result, transport = self.call(
                            mode, start=f'2026-09-09T14:00:00{fraction}{suffix}',
                            end=f'2026-09-09T15:00:00{fraction}{suffix}')
                        self.assertFalse(hasattr(result, 'error'), vars(result))
                        payload = transport.call_args.kwargs['json']
                        expected = datetime(2026, 9, 9, hour, minute,
                                            microsecond=123000 if fraction else 0, tzinfo=timezone.utc)
                        self.assert_instant(payload['start'], expected)
                        self.assert_instant(payload['end'], expected + timedelta(hours=1))

    def test_default_duration_preserves_instant(self):
        for suffix, hour, minute in (('+05:30', 8, 30), ('-04:00', 18, 0), ('Z', 14, 0)):
            with self.subTest(suffix=suffix):
                result, transport = self.call('create', start=f'2026-09-09T14:00:00.123{suffix}')
                self.assertFalse(hasattr(result, 'error'), vars(result))
                payload = transport.call_args.kwargs['json']
                expected = datetime(2026, 9, 9, hour, minute, microsecond=123000, tzinfo=timezone.utc)
                self.assert_instant(payload['start'], expected)
                self.assert_instant(payload['end'], expected + timedelta(hours=1))

    def test_naive_datetime_still_uses_utc(self):
        for mode in ('create', 'update'):
            for fraction in ('', '.123'):
                with self.subTest(mode=mode, fraction=fraction):
                    result, transport = self.call(mode, start=f'2026-09-09T14:00:00{fraction}')
                    self.assertFalse(hasattr(result, 'error'), vars(result))
                    self.assert_instant(transport.call_args.kwargs['json']['start'],
                                        datetime(2026, 9, 9, 14, microsecond=123000 if fraction else 0,
                                                 tzinfo=timezone.utc))

    def test_date_only_remains_all_day(self):
        for mode in ('create', 'update'):
            with self.subTest(mode=mode):
                result, transport = self.call(mode, start='2026-09-09')
                self.assertFalse(hasattr(result, 'error'), vars(result))
                payload = transport.call_args.kwargs['json']
                self.assertEqual(payload['start'], {'date': '2026-09-09'})
                if mode == 'create':
                    self.assertEqual(payload['end'], {'date': '2026-09-10'})

    def test_invalid_start_or_end_never_writes_event(self):
        for mode in ('create', 'update'):
            for field in ('start', 'end'):
                with self.subTest(mode=mode, field=field):
                    fields = dict(start='2026-09-09T14:00:00+05:30')
                    fields[field] = 'not-a-date'
                    result, transport = self.call(mode, **fields)
                    self.assertTrue(result.error)
                    transport.assert_not_called()


if __name__ == '__main__':
    unittest.main()
