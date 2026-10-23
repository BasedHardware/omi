"""Exercise the actual installer with hermetic network/package-manager commands."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('native-audio-replay-deps.sh')


class NativeAudioReplayDepsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.events = self.root / 'events'
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        EVENTS=str(self.events), STATE=str(self.root / 'attempts'))
        self.command('sudo', 'exec "$@"')
        self.command('sleep', 'echo "sleep $*" >> "$EVENTS"')
        self.command('dpkg', 'echo dpkg >> "$EVENTS"; exit "${DPKG_STATUS:-0}"')
        self.command('ffmpeg', 'echo ffmpeg >> "$EVENTS"')
        self.command('python3', 'echo opus >> "$EVENTS"')
        self.command('timeout', '''
echo "timeout $*" >> "$EVENTS"
n=0; if [[ -f $STATE ]]; then n=$(cat "$STATE"); fi
n=$((n + 1)); echo "$n" > "$STATE"
if ((n <= ${FETCH_FAILURES:-0})); then exit 124; fi
shift 3
exec "$@"
''')
        self.command('apt-get', '''
echo "apt $*" >> "$EVENTS"
for arg in "$@"; do
  case "$arg" in Dir::Cache::archives=*) cache=${arg#*=} ;; esac
done
if [[ " $* " == *' --download-only '* ]]; then
  printf package > "$cache/ffmpeg.deb"
fi
''')

    def command(self, name, body):
        p = self.bin / name
        p.write_text('#!/usr/bin/env bash\nset -eu\n' + body + '\n')
        p.chmod(0o755)

    def run_installer(self, **env):
        return subprocess.run(['bash', str(SCRIPT), str(self.cache)],
                              env=dict(self.env, **env), text=True, capture_output=True)

    def cached_package(self):
        (self.cache / 'ffmpeg.deb').write_bytes(b'package')
        digest = hashlib.sha256(b'package').hexdigest()
        (self.cache / 'SHA256SUMS').write_text(f'{digest}  ./ffmpeg.deb\n')

    def test_cold_fetch_then_warm_install_has_no_network(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.cache / 'SHA256SUMS').is_file())
        self.events.write_text('')
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events.read_text().splitlines(), ['dpkg', 'ffmpeg', 'opus'])

    def test_timeout_retries_with_backoff_then_succeeds(self):
        result = self.run_installer(FETCH_FAILURES='2')
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events.read_text()
        self.assertEqual(events.count('timeout '), 3)
        self.assertIn('sleep 5\n', events)
        self.assertIn('sleep 10\n', events)

    def test_exhaustion_is_a_failure_and_never_installs_or_saves(self):
        result = self.run_installer(FETCH_FAILURES='3')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('failed after 3 attempts', result.stderr)
        self.assertEqual(self.events.read_text().count('timeout '), 3)
        self.assertNotIn('dpkg', self.events.read_text())
        self.assertFalse((self.cache / 'SHA256SUMS').exists())

    def test_corrupt_cache_fails_without_fetch_or_install(self):
        self.cached_package()
        (self.cache / 'ffmpeg.deb').write_bytes(b'corrupt')
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertFalse(self.events.exists())

    def test_install_failure_is_not_repaired_over_network(self):
        self.cached_package()
        result = self.run_installer(DPKG_STATUS='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.events.read_text().splitlines(), ['dpkg'])

    def test_unverified_cache_is_rejected(self):
        (self.cache / 'ffmpeg.deb').write_bytes(b'package')
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no checksum manifest', result.stderr)
        self.assertFalse(self.events.exists())


if __name__ == '__main__':
    unittest.main()
