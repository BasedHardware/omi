#!/usr/bin/env python3
"""Every env var upstream declares for a deployed service is either declared by us, or written off.

Upstream does not decide its runtime configuration in code. It declares it in
``backend/deploy/runtime_env.yaml`` -- one entry per variable per deployed service -- and its deploy
pipeline refuses to ship a service whose required variables are missing
(``scripts/runtime_env_validation/manifest.py``). That file is where ``MEMORY_ENABLED: 'on'`` lives.

Our deployment does not go through that pipeline: compose and Helm are ours, and their environment was
assembled by discovery -- bring the stack up, see what fails, add the variable. Nothing ever walked
upstream's list. So for every variable upstream declares and we do not, we silently take the code's
default, and defaults are not neutral. Two measured consequences of exactly that, on this stack:

  * ``MEMORY_ENABLED`` unset -> ``rollout_mode_env_value()`` returns ``off`` -> every memory write
    answers 503 "Service temporarily unavailable", readiness passes, nothing says so. It surfaced
    only because ten tests in four upstream E2E files failed; setting it turns all ten green.
  * ``MEMORY_V3_CURSOR_SECRET`` unset -> cursor pagination raises 503 "Memory cursor unavailable".
    The list endpoint falls back to an offset read for the FIRST page only, so the failure is
    invisible until a user pages.

Neither is a bug in upstream's code. Both are a variable nobody looked at.

So this guard walks the list mechanically and ratchets it. A variable upstream declares must be one of:

  1. declared by us (an env-file example, a compose ``environment:`` entry, or the Helm ConfigMap), or
  2. present in the baseline with a written note saying why not.

The note matters more than the count: ``unreviewed`` is the honest default, and the number of
``unreviewed`` entries is the size of the debt. A new upstream variable is in neither place, so it
fails CI instead of arriving as a silent default -- which is the whole point.

The baseline also self-cleans: an entry that is no longer needed (upstream dropped the variable, or we
now declare it) is reported too. A ratchet list that only grows becomes the stale residual list that
already cost us three real failures read as known noise.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = Path('.github/scripts/runtime_env_parity_baseline.json')

UPSTREAM_DECLARATION = Path('backend/deploy/runtime_env.yaml')

# Where WE declare the backend's environment. Committed files only: the real env-files are gitignored
# (they carry secrets), so the ``.example`` files are the operator-facing contract and the thing that
# has to mention a variable for an operator to ever set it.
OUR_DECLARATIONS = (
    Path('deploy/onprem/backend.env.base.example'),
    Path('deploy/onprem/backend.env.dev.example'),
    Path('deploy/onprem/backend.env.prod.example'),
    Path('deploy/onprem/backend.env.prod.cloud.example'),
    Path('deploy/onprem/backend.env.seed.example'),
    Path('deploy/onprem/compose.base.yaml'),
    Path('deploy/onprem/compose.selfhost.yaml'),
    Path('deploy/onprem/compose.dev.yaml'),
    Path('deploy/onprem/compose.prod.yaml'),
    Path('deploy/onprem/helm/omi-oss/templates/backend-configmap.yaml'),
    Path('deploy/onprem/helm/omi-oss/templates/backend-secret.yaml'),
    Path('deploy/onprem/helm/omi-oss/templates/llm-gateway.yaml'),
)

ENV_NAME = r'[A-Z][A-Z0-9_]{2,}'

# The honest default note: "nobody has looked at this yet". The count of these IS the debt.
UNREVIEWED = 'unreviewed'

# Uppercase keys in runtime_env.yaml that name a section or a gcloud flag, not an env var.
NOT_ENV_KEYS = frozenset({'ENV', 'PROJECT_ID', 'REGION', 'SERVICE'} - {'ENV'})


def upstream_declared(text: str) -> set[str]:
    """Env var names upstream declares, read as keys of its runtime-env declaration.

    Deliberately regex over the text rather than a YAML load: the file mixes env maps with gcloud
    flag maps and comment-only stanzas, a loader would need to model all three, and a name that
    appears as a key is declared whichever stanza it sits in. Over-collecting here is the safe
    direction (it can only ask us to write a note); under-collecting would hide a variable.
    """
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        match = re.match(rf'^({ENV_NAME}):', stripped)
        if match and match.group(1) not in NOT_ENV_KEYS:
            names.add(match.group(1))
        # ``--set-env-vars: A=1,B=2`` and ``--remove-env-vars: A,B`` list names inline.
        inline = re.match(r'^--(?:set|remove|update)-env-vars:\s*(.+)$', stripped)
        if inline:
            for token in re.split(r'[,\s]+', inline.group(1)):
                name = token.split('=', 1)[0].strip().strip('"\'')
                if re.fullmatch(ENV_NAME, name) and name not in NOT_ENV_KEYS:
                    names.add(name)
    return names


# Compose services whose environment IS the backend's. Another service's environment (mongo's
# MONGO_INITDB_*, keycloak's KC_*) must not count as us declaring a backend variable -- that would
# hide a gap, the one error direction that matters here.
BACKEND_COMPOSE_SERVICES = frozenset({'backend', 'llm_gateway', 'memory_maintenance', 'seed'})


def ours_declared(texts: dict[str, str]) -> set[str]:
    """Env var names WE declare for the backend, given {path: text}.

    Precise on purpose, stdlib only (like its five sibling guards -- no YAML dependency):

      * env-file examples: ``NAME=`` at the start of a line;
      * compose: an indented ``NAME:`` key, but only inside a service that IS the backend
        (BACKEND_COMPOSE_SERVICES) -- tracked with a small indentation state machine;
      * Helm templates: any indented ``NAME:`` key (a backend ConfigMap/Secret holds nothing else).

    A ``${NAME}`` interpolation is a *use*, not a declaration, and must not count.
    """
    names: set[str] = set()
    for path, text in texts.items():
        is_env_file = path.endswith('.example') or '.env' in path
        is_compose = '/compose.' in path or path.startswith('compose.')
        service: str | None = None
        for line in text.splitlines():
            if line.lstrip().startswith('#'):
                continue
            if is_env_file:
                match = re.match(rf'^({ENV_NAME})=', line)
                if match:
                    names.add(match.group(1))
                continue
            if is_compose:
                # A two-space key under ``services:`` names a service; deeper keys belong to it.
                service_start = re.match(r'^  ([a-z][a-z0-9_-]*):\s*$', line)
                if service_start:
                    service = service_start.group(1)
                    continue
                if re.match(r'^[a-z]', line):  # a new top-level block (volumes:, include:, ...)
                    service = None
                    continue
                if service not in BACKEND_COMPOSE_SERVICES:
                    continue
            match = re.match(rf'^\s+({ENV_NAME}):', line)
            if match:
                names.add(match.group(1))
    return names


def check(upstream_text: str, our_texts: dict[str, str], baseline: dict[str, str]) -> dict[str, list[str]]:
    """Classify every upstream-declared variable. Pure over strings so tests need no repository.

    Returns ``{'undeclared': [...], 'stale_baseline': [...], 'unreviewed': [...]}``:
      undeclared      -- upstream declares it, we do not, and no baseline note explains why (FAILS)
      stale_baseline  -- a baseline note for a variable we now declare, or upstream no longer does
      unreviewed      -- baseline notes still carrying the default marker (the size of the debt)
    """
    upstream = upstream_declared(upstream_text)
    ours = ours_declared(our_texts)
    missing = upstream - ours
    return {
        'undeclared': sorted(missing - set(baseline)),
        'stale_baseline': sorted(set(baseline) - missing),
        'unreviewed': sorted(name for name, note in baseline.items() if note.strip() == UNREVIEWED),
    }


def load_baseline(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding='utf-8').strip()
    if not raw:
        # Almost always ``--print-baseline > <the baseline>``: the shell truncates the file before the
        # script reads it. Say so instead of reporting a JSON syntax error at char 0.
        raise ValueError(f'baseline file is empty: {path} (redirect to a temp file, then move it)')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value.strip() for key, value in payload.items()
    ):
        raise ValueError(f'baseline must be a JSON object of variable-to-nonempty-note entries: {path}')
    return payload


def _read(repository_root: Path) -> tuple[str, dict[str, str]]:
    upstream_text = (repository_root / UPSTREAM_DECLARATION).read_text(encoding='utf-8')
    our_texts: dict[str, str] = {}
    for relative in OUR_DECLARATIONS:
        path = repository_root / relative
        if path.exists():
            our_texts[str(relative)] = path.read_text(encoding='utf-8')
    return upstream_text, our_texts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--print-baseline', action='store_true', help='emit a baseline for the current tree')
    parser.add_argument('--report', action='store_true', help='counts plus the unreviewed list')
    args = parser.parse_args()

    repository_root = args.root.resolve()
    upstream_text, our_texts = _read(repository_root)
    baseline_path = args.baseline if args.baseline.is_absolute() else repository_root / args.baseline

    if args.print_baseline:
        missing = upstream_declared(upstream_text) - ours_declared(our_texts)
        try:
            existing = load_baseline(baseline_path)
        except (ValueError, OSError):
            # Regenerating must work from a missing, empty or corrupt baseline -- otherwise the only
            # way to repair one is by hand, which is when notes get lost.
            existing = {}
        print(json.dumps({name: existing.get(name, UNREVIEWED) for name in sorted(missing)}, indent=2))
        return 0

    baseline = load_baseline(baseline_path)
    result = check(upstream_text, our_texts, baseline)

    if args.report:
        print(f'upstream declares : {len(upstream_declared(upstream_text))}')
        print(f'we declare        : {len(ours_declared(our_texts))}')
        print(f'written off       : {len(baseline) - len(result["unreviewed"])}')
        print(f'UNREVIEWED        : {len(result["unreviewed"])}')
        print(*(f'  {name}' for name in result['unreviewed']), sep='\n')
        return 0

    if not result['undeclared'] and not result['stale_baseline']:
        return 0
    if result['undeclared']:
        print('FAIL: upstream declares a runtime env var we neither set nor wrote off.')
        print('Taking the code default is a decision; make it one. Either declare it in')
        print('deploy/onprem/ (env-file example, compose, or the Helm ConfigMap), or add it to')
        print(f'{DEFAULT_BASELINE} with a note saying why the default is right for us.')
        print(*(f'  {name}' for name in result['undeclared']), sep='\n')
    if result['stale_baseline']:
        print('FAIL: baseline notes for variables that no longer need one (we declare them now, or')
        print('upstream dropped them). Remove the entries -- a list that only grows rots into noise.')
        print(*(f'  {name}' for name in result['stale_baseline']), sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
