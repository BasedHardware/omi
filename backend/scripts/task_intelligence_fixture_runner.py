#!/usr/bin/env python3
"""Run hermetic task-intelligence fixtures and emit canonical JSON."""

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.task_intelligence.contracts import load_fixture
from utils.task_intelligence.fixture_runner import run_fixture_suite


def main() -> None:
    result = run_fixture_suite(
        capture=load_fixture('capture_v2.json'),
        association=load_fixture('association_v1.json'),
        ranking=load_fixture('ranking_v2.json'),
    )
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
