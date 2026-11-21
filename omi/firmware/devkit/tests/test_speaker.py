#!/usr/bin/env python3
"""Execute the DevKit PCM parser and DMA lifecycle with a deterministic I2S driver.

The production functions are compiled directly, so slab ownership, validation,
notification timing and the absence of a fixed sleep are exercised without a jig.
"""
from pathlib import Path
import os
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'speaker.c'


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    source = SOURCE.read_text()
    functions = '\n'.join(function(source, signature) for signature in (
        'static int play_pcm_block(', 'static void play_pending_block(',
        'int speak(', 'void speaker_reset_stream(',
    ))
    harness = Path(__file__).with_suffix('.c').read_text().replace('/* PRODUCTION */', functions)
    with tempfile.TemporaryDirectory(prefix='speaker-host-') as output:
        path = Path(output)
        (path / 'test.c').write_text(harness)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all', str(path / 'test.c'),
                        '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    main()
