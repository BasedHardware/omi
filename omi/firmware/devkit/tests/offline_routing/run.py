#!/usr/bin/env python3
"""Execute production C audio routing functions with deterministic I/O faults."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "src"


def function(filename, name):
    source = (SOURCE / filename).read_text()
    match = re.search(r"^(?:static )?void " + name + r"\([^;]*?\)\s*\{", source, re.M)
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


with tempfile.TemporaryDirectory(prefix="devkit-routing-") as tmp:
    directory = Path(tmp)
    (directory / "production.inc").write_text("\n".join([
        function("transport.c", "pusher"),
    ]))
    binary = directory / "test"
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-I", tmp, str(HERE / "test_routing.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
