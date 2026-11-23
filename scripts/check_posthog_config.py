#!/usr/bin/env python3
"""PostHog ingestion config guard (SCA-3665); stdlib only, no network.

contracts/analytics/posthog.json is the single source of truth for PostHog
sampling and warehouse syncs. This check fails when:
  - an event the config keeps at 100% has no measured est_events_per_day or no reader;
  - a debug/ops event (by purpose or by name) is kept above 2% without an
    unexpired waiver signed by David Zhang;
  - the estimated monthly cost exceeds budget.monthly_usd (a budget.ceiling
    counts only with an unexpired waiver signed by David Zhang);
  - a warehouse schema full-refreshes more than 1M rows per run;
  - a later sampling stage would overwrite omi_sample_pct with a looser rate
    than an earlier stage applied, so reweighting readers would read wrong.
It prints `PostHog estimate: $X/mo (base $Y/mo, delta $Z)` against the
merge-base copy of the file, so every PR's cost is visible in its CI log.
When the diff does not touch the config or this guard, findings are printed as
warnings: an expiring waiver must not block unrelated mobile PRs.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'contracts/analytics/posthog.json'
OWNED_PATHS = (SOURCE, 'scripts/check_posthog_config.py', 'scripts/test_check_posthog_config.py', 'scripts/posthog')
SAMPLE_CEILING = 2.0
WAIVER_SIGNER = 'David Zhang'
FULL_REFRESH_ROW_LIMIT = 1_000_000
PURPOSES = ('product', 'debug', 'ops')
KINDS = ('keep_list', 'sample', 'drop', 'unmanaged')
# Matched against whole name tokens (split on spaces, _ and -), ignoring case.
# Sample and Daily only as the last token: periodic telemetry is named
# "Phone Battery Sample" or "Mobile Device Health Daily", while
# "Daily Summary Detail Viewed" is a product feature.
DEBUG_TOKENS = frozenset(t.lower() for t in (
    'Failed', 'Error', 'Health', 'Wedge', 'Stuck', 'Diagnostic', 'Retry',
    'Throttled', '401', 'Observation', 'Coverage', 'fallback'))
DEBUG_SUFFIXES = frozenset(('sample', 'daily'))
# Mirrors the keep-list function's hog source: these names pass the default
# sample without being listed. They are not editable through inputs.
HOG_MARKERS = ('onboard', 'paywall', 'subscri', 'purchase', 'checkout', 'trial', 'plan',
               'pricing', 'upgrade', 'signup', 'sign up', 'sign in', 'login', 'experiment')


def debug_name(name):
    tokens = [t.lower() for t in re.split(r'[^A-Za-z0-9]+', name) if t]
    return any(t in DEBUG_TOKENS for t in tokens) or bool(tokens and tokens[-1] in DEBUG_SUFFIXES)


def rule_kept(name):
    """True when the keep-list hog source keeps the name without listing it."""
    return (name.startswith('$') and name != '$rageclick') or any(m in name.lower() for m in HOG_MARKERS)


def stages(doc):
    return [f for f in sorted(doc['functions'], key=lambda f: f['execution_order'])
            if f.get('enabled', True) and f['kind'] != 'unmanaged']


def effective(doc, name):
    """(effective pct, omi_sample_pct tag a reader sees, list of (stage id, pct)) for one event."""
    pct, tag, applied = 100.0, None, []
    for f in stages(doc):
        if f['kind'] == 'keep_list':
            if name in f['events'] or rule_kept(name):
                continue
        elif name not in f['events']:
            continue
        p = float(f['pct'])
        applied.append((f['id'], p))
        pct = min(pct, p)
        if 0 < p < 100:
            tag = p
    return pct, tag, applied


def tiered(units, tiers):
    cost, floor = 0.0, 0
    for upper, price in tiers:
        top = units if upper is None else min(units, upper)
        if top > floor:
            cost += (top - floor) * price
        if upper is None or units <= upper:
            break
        floor = upper
    return cost


def estimate(doc, with_planned=False):
    """Monthly cost. with_planned applies budget.planned savings (changes not yet made)."""
    budget = doc['budget']
    days = budget.get('days_per_month', 30)
    planned = budget.get('planned', []) if with_planned else []
    event_saving, flag_saving = {}, 0
    for item in planned:
        saving = item.get('saving', {})
        for name, per_day in saving.get('events_per_day', {}).items():
            event_saving[name] = event_saving.get(name, 0) + per_day
        flag_saving += saving.get('feature_flag_requests_per_month', 0)
    events = identified = 0.0
    for name, entry in doc['events'].items():
        est = entry.get('est_events_per_day')
        est = est if isinstance(est, (int, float)) and est > 0 else 0  # validate() reports bad values
        est = max(0, est - event_saving.get(name, 0))
        stored = est * effective(doc, name)[0] / 100 * days
        events += stored
        if entry.get('identified'):
            identified += stored
    rows = sum(s['est_rows_per_run'] * s.get('runs_per_month', 1)
               for s in doc['warehouse']['schemas'] if s.get('should_sync'))
    rows += doc['warehouse'].get('unmanaged', {}).get('est_rows_per_month', 0)
    tiers = budget['tiers']
    parts = {
        'events': tiered(events, tiers['events']),
        'identified': tiered(identified, tiers['identified_events']),
        'flags': tiered(max(0, budget.get('feature_flag_requests_per_month', 0) - flag_saving), tiers['feature_flag_requests']),
        'warehouse': rows * budget['warehouse_usd_per_row'],
        'other': sum(budget.get('other_monthly_usd', {}).values()),
    }
    parts['total'] = sum(parts.values())
    parts['events_per_month'] = events
    parts['identified_per_month'] = identified
    parts['warehouse_rows_per_month'] = rows
    return parts


def waiver_ok(waiver, today):
    if not isinstance(waiver, dict) or waiver.get('by') != WAIVER_SIGNER or not waiver.get('reason'):
        return False
    try:
        dt.date.fromisoformat(waiver['date'])
        return dt.date.fromisoformat(waiver['expires']) >= today
    except (KeyError, TypeError, ValueError):
        return False


def budget_errors(doc, today, cost):
    """Over budget fails. A budget.ceiling counts only with an unexpired waiver signed by David Zhang."""
    budget = doc['budget']
    ceiling = budget.get('ceiling')
    errors = []
    signed = False
    if ceiling is not None:
        try:
            until = dt.date.fromisoformat(ceiling['until'])
            usd = float(ceiling['usd'])
        except (KeyError, TypeError, ValueError):
            return ['budget.ceiling: needs usd, until (YYYY-MM-DD), reason and a waiver signed by David Zhang']
        signed = waiver_ok(ceiling.get('waiver'), today) and until >= today
        if not signed:
            errors.append(f'budget.ceiling: a ceiling needs an unexpired waiver signed by {WAIVER_SIGNER}')
    if cost['total'] > budget['monthly_usd'] and not (signed and cost['total'] <= usd):
        errors.append(f"budget: estimated ${cost['total']:,.0f}/mo exceeds budget.monthly_usd ${budget['monthly_usd']:,}")
    return errors


def validate(doc, today):
    errors = []
    ids = [f['id'] for f in doc['functions']]
    if len(set(ids)) != len(ids):
        errors.append('functions: ids must be unique')
    keep = [f for f in doc['functions'] if f['kind'] == 'keep_list']
    if len(keep) != 1:
        errors.append('functions: exactly one keep_list function is required')
    for f in doc['functions']:
        if f['kind'] not in KINDS:
            errors.append(f"{f['id']}: kind must be one of {', '.join(KINDS)}")
        elif f['kind'] != 'unmanaged' and not 0 <= float(f['pct']) <= 100:
            errors.append(f"{f['id']}: pct must be within 0..100")
        elif f['kind'] == 'drop' and float(f['pct']) != 0:
            errors.append(f"{f['id']}: a drop function has pct 0")
    if errors:
        return errors
    events = doc['events']
    named = set(events)
    for f in stages(doc):
        named.update(f['events'])
    for name in sorted(named):
        pct, tag, applied = effective(doc, name)
        entry = events.get(name)
        listed = name in keep[0]['events']
        est = (entry or {}).get('est_events_per_day')
        if entry is not None and est is not None and (not isinstance(est, int) or est < 0):
            errors.append(f'{name}: est_events_per_day must be a non-negative integer')
            continue
        if pct > SAMPLE_CEILING and not isinstance(est, int):
            errors.append(f'{name}: kept at {pct:g}% without a measured est_events_per_day (7-day HogQL count reweighted by omi_sample_pct)')
            continue
        if entry is None:
            continue
        if pct > 0 and tag is not None and tag != pct:
            errors.append(f'{name}: omi_sample_pct would read {tag:g} but the event is kept at {pct:g}% ({applied}); a later stage must not loosen an earlier one. List it in the keep-list so only its own sampler applies')
        if pct >= 100 and listed and not entry.get('reader'):
            errors.append(f'{name}: kept at 100% with no reader (insight short_id, file path or alert uid)')
        if pct <= SAMPLE_CEILING or (rule_kept(name) and not listed):
            continue
        purpose = entry.get('purpose')
        if purpose not in PURPOSES:
            errors.append(f'{name}: kept at {pct:g}% needs purpose product | debug | ops')
        elif (purpose != 'product' or debug_name(name)) and not waiver_ok(entry.get('waiver'), today):
            errors.append(f'{name}: {purpose if purpose != "product" else "debug-named"} event kept at {pct:g}% (> {SAMPLE_CEILING:g}%) needs an unexpired waiver signed by {WAIVER_SIGNER}; PostHog is for product analytics only, send debugging signals to the client collector')
    for schema in doc['warehouse']['schemas']:
        if schema.get('should_sync') and schema.get('sync_type') == 'full_refresh' and schema.get('est_rows_per_run', 0) > FULL_REFRESH_ROW_LIMIT:
            errors.append(f"warehouse {schema['name']}: full_refresh re-bills {schema['est_rows_per_run']:,} rows every run; use incremental/append or a smaller view")
    return errors + budget_errors(doc, today, estimate(doc))


def merge_base(base):
    found = subprocess.run(['git', 'merge-base', 'HEAD', base], cwd=ROOT, capture_output=True, text=True)
    return found.stdout.strip() if found.returncode == 0 else base


def base_doc(ref):
    """The file at ref, or None when it did not exist there."""
    shown = subprocess.run(['git', 'show', f'{ref}:{SOURCE}'], cwd=ROOT, capture_output=True, text=True)
    return json.loads(shown.stdout) if shown.returncode == 0 else None


def owned_change(ref):
    diff = subprocess.run(['git', 'diff', '--name-only', ref, '--', *OWNED_PATHS], cwd=ROOT, capture_output=True, text=True)
    new = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '--', *OWNED_PATHS], cwd=ROOT, capture_output=True, text=True)
    return diff.returncode != 0 or bool(diff.stdout.strip() or new.stdout.strip())


def run(path, base, today, enforce=None):
    """Print the estimate and findings; return the findings that fail the check."""
    doc = json.loads(Path(path).read_text())
    ref = merge_base(base) if base else None
    prior = base_doc(ref) if ref else None
    errors = validate(doc, today)
    cost = estimate(doc)
    old = estimate(prior)['total'] if prior else 0.0
    if enforce is None:
        enforce = ref is None or owned_change(ref)
    print(f"PostHog estimate: ${cost['total']:,.0f}/mo (base ${old:,.0f}/mo, delta ${cost['total'] - old:+,.0f})")
    print(f"  events {cost['events_per_month'] / 1e6:.2f}M/mo ${cost['events']:,.0f}; identified {cost['identified_per_month'] / 1e6:.2f}M/mo ${cost['identified']:,.0f}; "
          f"flags ${cost['flags']:,.0f}; warehouse {cost['warehouse_rows_per_month'] / 1e6:.2f}M rows ${cost['warehouse']:,.0f}; other ${cost['other']:,.0f}")
    if doc['budget'].get('planned'):
        ids = ', '.join(item['id'] for item in doc['budget']['planned'])
        print(f"  with planned changes ({ids}): ${estimate(doc, with_planned=True)['total']:,.0f}/mo")
    for error in errors:
        print(error if enforce else f'warning (PostHog config unchanged in this diff): {error}')
    return errors if enforce else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='origin/main')
    parser.add_argument('--file', default=str(ROOT / SOURCE))
    parser.add_argument('--today', help='UTC date for waiver expiry (default: today)')
    args = parser.parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    return bool(run(args.file, args.base, today))


if __name__ == '__main__':
    raise SystemExit(main())
