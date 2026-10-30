#!/usr/bin/env python3
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from check_plugin_request_timeouts import unbounded_calls

SCRIPT = Path(__file__).with_name('check_plugin_request_timeouts.py')
BARE = 'import requests\nrequests.get(url)\n'
BOUNDED = 'import requests\nrequests.get(url, timeout=(5, 30))\n'


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


class RootTests(unittest.TestCase):
    def run_in(self, root):
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=root, capture_output=True, text=True)

    def test_the_mcp_server_is_scanned_along_with_the_plugins(self):
        with tempfile.TemporaryDirectory() as root:
            files = [Path(root, 'plugins', 'app', 'main.py'), Path(root, 'mcp', 'src', 'server', 'main.py')]
            for path in files:
                path.parent.mkdir(parents=True)
                path.write_text(BARE)
            result = self.run_in(root)
            reported = result.stderr.replace('\\', '/')
            self.assertEqual(result.returncode, 1)
            self.assertIn('plugins/app/main.py:2', reported)
            self.assertIn('mcp/src/server/main.py:2', reported)

            for path in files:
                path.write_text(BOUNDED)
            self.assertEqual(self.run_in(root).returncode, 0)

    def test_test_files_installed_packages_and_other_trees_are_left_out(self):
        with tempfile.TemporaryDirectory() as root:
            for relative in ['mcp/tests/test_server.py', 'mcp/.venv/lib/site-packages/pkg/mod.py', 'backend/main.py']:
                path = Path(root, relative)
                path.parent.mkdir(parents=True)
                path.write_text(BARE)
            Path(root, 'plugins').mkdir()
            self.assertEqual(self.run_in(root).returncode, 0)


if __name__ == '__main__':
    unittest.main()
