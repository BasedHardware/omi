#!/usr/bin/env python3
"""Rebase committed SwiftLint file URLs onto this checkout without dropping entries."""
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

source, ios_dir, output = map(Path, sys.argv[1:])
data = json.loads(source.read_text())
if not isinstance(data, list):
    raise ValueError("SwiftLint baseline must be an array")
for entry in data:
    location = entry["violation"]["location"]
    parsed = urlparse(location["file"])
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise ValueError("invalid baseline URL")
    path = Path(unquote(parsed.path))
    parts = path.parts
    indices = [i for i in range(len(parts)-1) if parts[i:i+2] == ("app", "ios")]
    if not indices:
        raise ValueError("baseline entry is outside app/ios")
    relative = Path(*parts[indices[-1]+2:])
    if not relative.parts or ".." in relative.parts:
        raise ValueError("invalid baseline path")
    location["file"] = (ios_dir.resolve() / relative).as_uri()
output.write_text(json.dumps(data, indent=2) + "\n")
