"""Exercise public imports in fresh interpreters, without optional STT packages."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class TestTranscribeExport(unittest.TestCase):
    def run_example(self, imports):
        source = imports + textwrap.dedent(
            r"""
            import asyncio
            import sys

            assert callable(transcribe), type(transcribe)
            assert not ({'bleak', 'opuslib', 'whisper', 'websockets'} & sys.modules.keys())

            class TranscriptReceived(Exception):
                pass

            async def main():
                audio = asyncio.Queue()
                pcm = b'\x00\x00' * (16000 * 5)
                audio.put_nowait(pcm)
                received = []

                def runner(data):
                    assert data == pcm
                    return 'local transcript'

                def on_transcript(text):
                    received.append(text)
                    raise TranscriptReceived

                try:
                    await transcribe(audio, '', on_transcript, engine='whisper', runner=runner)
                except TranscriptReceived:
                    pass
                assert received == ['local transcript'], received

            asyncio.run(main())
            """
        )
        env = dict(os.environ)
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
        result = subprocess.run(
            [sys.executable, '-S', '-c', source],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_documented_from_import(self):
        self.run_example('from omi import transcribe\n')

    def test_repeated_package_attribute_access(self):
        self.run_example(
            'import omi\n'
            'first = omi.transcribe\n'
            'transcribe = omi.transcribe\n'
            'assert first is transcribe\n'
        )

    def test_submodule_import_before_public_import(self):
        self.run_example(
            'from omi.transcribe import transcribe as direct\n'
            'from omi import transcribe\n'
            'assert transcribe is direct\n'
        )


if __name__ == '__main__':
    unittest.main()
