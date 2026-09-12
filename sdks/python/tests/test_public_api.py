"""Public `transcribe` export must be the async function, not the submodule."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class TestTranscribeExport(unittest.TestCase):
    def run_fresh(self, setup: str) -> None:
        source = setup + textwrap.dedent(
            r"""
            import asyncio
            import sys

            assert callable(transcribe), type(transcribe)
            assert not ({'bleak', 'opuslib', 'whisper', 'websockets'} & set(sys.modules))

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
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_documented_from_import(self) -> None:
        self.run_fresh('from omi import transcribe\n')

    def test_repeated_package_attribute(self) -> None:
        self.run_fresh(
            'import omi\n'
            'first = omi.transcribe\n'
            'transcribe = omi.transcribe\n'
            'assert first is transcribe\n'
        )

    def test_submodule_import_does_not_replace_public_function(self) -> None:
        self.run_fresh(
            'from omi.transcribe import transcribe as direct\n'
            'from omi import transcribe\n'
            'assert transcribe is direct\n'
        )


if __name__ == '__main__':
    unittest.main()
