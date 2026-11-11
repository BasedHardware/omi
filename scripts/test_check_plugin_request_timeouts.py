#!/usr/bin/env python3
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from check_plugin_request_timeouts import unbounded_calls


def scan(source):
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as handle:
        handle.write(source)
        path = Path(handle.name)
    try:
        return unbounded_calls(path)
    finally:
        path.unlink()


class ScannerTests(unittest.TestCase):
    def test_bare_call_is_reported_and_a_timeout_clears_it(self):
        self.assertEqual([c[1] for c in scan('import requests\nrequests.get(url)\n')], ['get'])
        self.assertEqual(scan('import requests\nrequests.get(url, timeout=5)\n'), [])
        self.assertEqual(scan('import requests\nrequests.post(url, json=b, timeout=(5, 30))\n'), [])

    def test_session_bound_to_requests_is_followed(self):
        source = 'import requests\nsession = requests.Session()\nsession.get(url)\n'
        self.assertEqual([c[1] for c in scan(source)], ['get'])
        self.assertEqual(scan('mapping = {}\nmapping.get("uid")\n'), [])

    def test_async_handlers_are_flagged_as_event_loop_blockers(self):
        source = 'import requests\nasync def callback():\n    requests.post(url, data=d)\n'
        self.assertEqual([(c[1], c[2]) for c in scan(source)], [('post', True)])
        sync = 'import requests\ndef helper():\n    requests.post(url, data=d)\n'
        self.assertEqual([(c[1], c[2]) for c in scan(sync)], [('post', False)])

    def test_an_upstream_that_accepts_and_never_answers_only_ends_on_a_timeout(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(2)
        accepted = []

        def accept():
            try:
                accepted.append(listener.accept()[0])
            except OSError:
                pass

        threading.Thread(target=accept, daemon=True).start()
        url = f'http://127.0.0.1:{listener.getsockname()[1]}/token'

        started = time.monotonic()
        with self.assertRaises((TimeoutError, socket.timeout, urllib.error.URLError)):
            urllib.request.urlopen(url, timeout=1)
        self.assertLess(time.monotonic() - started, 5)

        for sock in accepted:
            sock.close()
        listener.close()


if __name__ == '__main__':
    unittest.main()
