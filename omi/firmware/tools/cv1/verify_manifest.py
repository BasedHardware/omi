#!/usr/bin/env python3
"""Verify included payload hashes without SDK, network or hardware access."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent;m=json.loads((root/'FIXTURES.json').read_text())
for f in m['files']:
 p=(root/f['path']).resolve()
 if root not in p.parents or not p.is_file():raise SystemExit('missing/unsafe payload: '+f['path'])
 b=p.read_bytes()
 if len(b)!=f['bytes'] or hashlib.sha256(b).hexdigest()!=f['sha256']:raise SystemExit('mismatch: '+f['path'])
print('PASS: '+str(len(m['files']))+' public fixtures/dependency pins match manifest; no hardware access')
