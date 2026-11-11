"""Run from repository root with PYTHONPATH=backend and the backend test environment."""

import json
from pathlib import Path

from tests.unit.fixtures.speaker_abstention import speaker_cases
from tests.unit.fixtures.speaker_abstention_outputs import snapshot

root = Path(__file__).resolve().parent
for case in speaker_cases():
    (root / f'{case}.json').write_text(json.dumps(snapshot(case), indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {case}.json')
