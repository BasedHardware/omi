#!/usr/bin/env python3
"""Execute production C recording/write functions with deterministic I/O faults."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "src"


def function(filename, name):
    source = (SOURCE / filename).read_text()
    match = re.search(r"^(?:static )?(?:int|bool) " + name + r"\([^;]*?\)\s*\{", source, re.M)
    if not match:
        raise RuntimeError(f"Missing production function: {name}")
    start = match.start()
    end = match.end()
    depth = 1
    # Selected functions contain no braces in string literals/comments.
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


with tempfile.TemporaryDirectory(prefix="devkit-recording-") as tmp:
    directory = Path(tmp)
    (directory / "production.inc").write_text("\n".join([
        function("sdcard.c", "write_to_file"),
        function("sdcard.c", "initialize_audio_file"),
        function("transport.c", "write_to_storage"),
    ]))
    binary = directory / "test"
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", tmp, str(HERE / "test_recording.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
