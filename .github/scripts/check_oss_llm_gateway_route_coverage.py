#!/usr/bin/env python3
"""Every LLM feature the backend can request is pinned to OUR endpoint, or the omission is written down.

The on-prem chat posture (ADR-0035) is: the backend never names a model, it emits ``omi:auto:<feature>``
lane ids, and only the LLM gateway resolves a lane to a provider. What makes that safe is
``deploy/onprem/llm_gateway/generated_route_overrides.yaml``, mounted over the gateway's own copy.

The trap is what an OMISSION means there. The gateway synthesises a lane for **every configured feature**
(``_generated_feature_route_items`` iterates ``get_all_configured_features()``), and a feature with no
override keeps its **cloud** model and provider from the QoS table. So a missing entry is not "that feature
is unconfigured" -- it is a live route to a vendor through our own gateway, and the only thing stopping it
is the absence of that vendor's credentials.

Measured on this tree before the file was completed: **8 of 45** configured features had no override --
``app_integration``, ``followup``, ``onboarding``, ``session_titles``, ``translation``, ``trends`` (all to
gemini), ``wrapped_analysis`` (openrouter), ``web_search`` (perplexity). Live, each answered
``503 invalid_config``; with a GEMINI_API_KEY in the environment, six of them would have answered 200 from
Google. ``translation`` carries transcript text.

The earlier reading of this ("37 of 37 features covered, nothing uncovered") was measured against the wrong
base: upstream's own override file, which lists 37. Upstream does not have to override a feature to route
it -- its QoS table already points at a provider it owns. Ours has to, for every feature that exists. The
base is the configured-feature set, and that is what this guard uses.

Two rules, both mechanical:

  1. every configured feature is either covered by our override file, or carries a note in the baseline;
  2. every covered feature is pinned to ``provider: openai`` -- our OpenAI-compatible endpoint. Without
     this a "covered" entry could name gemini and the coverage count would look perfect while the lane
     went to a vendor. Coverage without this check measures the wrong thing.

The baseline self-cleans, like its siblings: a note for a feature we now cover is a failure too, because a
list that only grows becomes the stale residual list that already cost this project three real failures
read as known noise.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = Path('.github/scripts/llm_gateway_route_coverage_baseline.json')

# Where the backend's feature -> (model, provider) table lives. ``get_all_configured_features()`` is
# exactly ``_active_profile.keys() | _PINNED_FEATURES.keys()``, and every QoS profile is a copy of the
# same two-tier dict, so these two literals ARE the configured set.
FEATURE_TABLE_SOURCE = Path('backend/utils/llm/model_config.py')
FEATURE_TABLE_NAMES = ('_TWO_TIER_MODEL_PROFILE', '_PINNED_FEATURES')

OUR_OVERRIDES = Path('deploy/onprem/llm_gateway/generated_route_overrides.yaml')

# The provider our endpoint speaks. Anything else in our override file is a vendor by definition: the
# gateway's non-openai providers are google/anthropic/openrouter/perplexity, none of which can be pointed
# at an operator-run endpoint the way OPENAI_BASE_URL can.
OUR_PROVIDER = 'openai'

UNREVIEWED = 'unreviewed'


class GuardError(RuntimeError):
    """The guard could not measure. Never silently degrades to an empty set."""


def configured_features(source: str) -> set[str]:
    """Feature names from the QoS table literals, read with the AST.

    Deliberately NOT an import: this runs from the repository root with no backend environment, and
    importing that module drags in logging/os config for a question that is answered by two dict
    literals. A missing literal is an ERROR, not an empty set -- a guard that measures nothing and
    passes is worse than no guard, and a rename upstream is exactly how that happens.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        # A traceback would also fail CI, but the message would name ast.py instead of the file that
        # actually broke. Say which file and why.
        raise GuardError(f'cannot parse {FEATURE_TABLE_SOURCE}: {error}') from error
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in FEATURE_TABLE_NAMES:
                continue
            if not isinstance(node.value, ast.Dict):
                raise GuardError(f'{target.id} is no longer a dict literal in {FEATURE_TABLE_SOURCE}')
            keys: set[str] = set()
            for key in node.value.keys:
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    raise GuardError(f'{target.id} has a non-literal key in {FEATURE_TABLE_SOURCE}')
                keys.add(key.value)
            found[target.id] = keys

    missing = [name for name in FEATURE_TABLE_NAMES if name not in found]
    if missing:
        raise GuardError(
            f'{FEATURE_TABLE_SOURCE} no longer defines {", ".join(missing)}. '
            'The feature table moved or was renamed: point this guard at the new one instead of '
            'letting it measure an empty set.'
        )
    return set().union(*found.values())


def overridden_features(text: str) -> dict[str, str]:
    """{feature: provider} from our override file, read line-wise (stdlib only, like every sibling guard).

    The file's shape is fixed and flat -- ``- feature: <name>`` then ``primary: {provider: x, model: y}``
    -- so a regex pair is enough and keeps this script dependency-free. A feature whose provider cannot be
    read is reported as the empty string, which fails rule 2 rather than passing silently.
    """
    features: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            continue
        feature = re.match(r'\s*-\s*feature:\s*(\S+)\s*$', line)
        if feature:
            current = feature.group(1)
            features[current] = ''
            continue
        if current is None:
            continue
        provider = re.search(r'primary:\s*\{[^}]*provider:\s*([A-Za-z0-9_-]+)', line)
        if provider:
            features[current] = provider.group(1)
    return features


def check(table_source: str, overrides_text: str, baseline: dict[str, str]) -> dict[str, list[str]]:
    """Pure over strings so the tests need no repository.

    uncovered       -- a configured feature with no override and no baseline note (FAILS)
    vendor_pinned   -- an override that names a provider that is not ours (FAILS)
    unknown_feature -- an override for a feature the backend does not configure (FAILS: the gateway
                       itself raises ConfigValidationError on this, so catching it here is just faster)
    stale_baseline  -- a note for a feature we now cover, or that no longer exists
    unreviewed      -- notes still carrying the default marker: the size of the debt
    """
    configured = configured_features(table_source)
    overrides = overridden_features(overrides_text)
    uncovered = configured - set(overrides)
    return {
        'uncovered': sorted(uncovered - set(baseline)),
        'vendor_pinned': sorted(
            f'{feature} -> {provider or "unreadable"}'
            for feature, provider in overrides.items()
            if provider != OUR_PROVIDER
        ),
        'unknown_feature': sorted(set(overrides) - configured),
        'stale_baseline': sorted(set(baseline) - uncovered),
        'unreviewed': sorted(name for name, note in baseline.items() if note.strip() == UNREVIEWED),
    }


def load_baseline(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding='utf-8').strip()
    if not raw:
        raise ValueError(f'baseline file is empty: {path} (redirect to a temp file, then move it)')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value.strip() for key, value in payload.items()
    ):
        raise ValueError(f'baseline must be a JSON object of feature-to-nonempty-note entries: {path}')
    return payload


def _read(repository_root: Path) -> tuple[str, str]:
    return (
        (repository_root / FEATURE_TABLE_SOURCE).read_text(encoding='utf-8'),
        (repository_root / OUR_OVERRIDES).read_text(encoding='utf-8'),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--print-baseline', action='store_true', help='emit a baseline for the current tree')
    parser.add_argument('--report', action='store_true', help='counts plus the uncovered list')
    args = parser.parse_args()

    repository_root = args.root.resolve()
    table_source, overrides_text = _read(repository_root)
    baseline_path = args.baseline if args.baseline.is_absolute() else repository_root / args.baseline

    if args.print_baseline:
        uncovered = configured_features(table_source) - set(overridden_features(overrides_text))
        try:
            existing = load_baseline(baseline_path)
        except (ValueError, OSError):
            existing = {}
        print(json.dumps({name: existing.get(name, UNREVIEWED) for name in sorted(uncovered)}, indent=2))
        return 0

    baseline = load_baseline(baseline_path)
    result = check(table_source, overrides_text, baseline)

    if args.report:
        configured = configured_features(table_source)
        overrides = overridden_features(overrides_text)
        print(f'configured features : {len(configured)}')
        print(f'pinned to us        : {len(overrides)}')
        print(f'written off         : {len(baseline) - len(result["unreviewed"])}')
        print(f'UNREVIEWED          : {len(result["unreviewed"])}')
        print(*(f'  {name}' for name in result['unreviewed']), sep='\n')
        return 0

    failures = ('uncovered', 'vendor_pinned', 'unknown_feature', 'stale_baseline')
    if not any(result[key] for key in failures):
        return 0

    if result['uncovered']:
        print('FAIL: a configured LLM feature has no on-prem route override, so the gateway keeps its')
        print('CLOUD provider for that lane. Pin it in deploy/onprem/llm_gateway/generated_route_overrides.yaml')
        print(f'(provider: {OUR_PROVIDER}, model: your served model), or add it to {DEFAULT_BASELINE}')
        print('with a note saying why a vendor route is the right answer for it.')
        print(*(f'  {name}' for name in result['uncovered']), sep='\n')
    if result['vendor_pinned']:
        print(f'FAIL: an override names a provider that is not ours ({OUR_PROVIDER}). The lane is covered')
        print('on paper and routed to a vendor in fact.')
        print(*(f'  {name}' for name in result['vendor_pinned']), sep='\n')
    if result['unknown_feature']:
        print('FAIL: an override names a feature the backend does not configure. The gateway refuses to')
        print('load with this (ConfigValidationError: unknown feature), so the stack would not start.')
        print(*(f'  {name}' for name in result['unknown_feature']), sep='\n')
    if result['stale_baseline']:
        print('FAIL: baseline notes for features that no longer need one (we pin them now, or the')
        print('feature is gone). Remove the entries -- a list that only grows rots into noise.')
        print(*(f'  {name}' for name in result['stale_baseline']), sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
