"""Run from repository root with PYTHONPATH=backend and the backend test environment."""

import json
from pathlib import Path

from tests.unit.fixtures.speaker_abstention import speaker_cases
from tests.unit.fixtures.speaker_abstention_outputs import snapshot

root = Path(__file__).resolve().parents[3] / 'backend/tests/unit/fixtures/speaker_abstention_snapshots'
for case in speaker_cases():
    output = snapshot(case)
    target = root / f'{case}.json'
    if target.exists():
        baseline = json.loads(target.read_text())
        assert output['before'] == baseline['before'], f'{case}: rollback differs from the main-verified baseline'
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {case}.json')
