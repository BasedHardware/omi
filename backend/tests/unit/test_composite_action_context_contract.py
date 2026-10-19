"""Composite action context availability is independent of retired rollout gates."""

import re
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]


def test_no_composite_action_reads_a_context_it_cannot_access():
    """`vars` and `secrets` do not exist inside a composite action.

    GitHub rejects the whole action at load time ("Unrecognized named-value"), so the
    failure is not the step that used it but every workflow that calls the action.
    YAML parsing and string-level wiring tests both pass on such a file.
    """
    repo = BACKEND.parent
    offenders = []
    for path in sorted((repo / '.github/actions').glob('*/action.y*ml')):
        action = yaml.safe_load(path.read_text())
        if (action.get('runs') or {}).get('using') != 'composite':
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for expression in re.findall(r'\$\{\{(.*?)\}\}', line):
                if re.search(r'(?<![\w.])(vars|secrets)\.', expression):
                    offenders.append(f'{path.relative_to(repo)}:{number}: {expression.strip()}')
    assert not offenders, 'composite actions cannot read vars/secrets; pass an input instead:\n' + '\n'.join(offenders)
