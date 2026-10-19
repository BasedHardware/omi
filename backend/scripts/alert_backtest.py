#!/usr/bin/env python3
"""Read-only, bounded Grafana/Prometheus replay and offline admission lint.

Unsupported semantics fail closed. Episodes are alert-instance transitions, not
Telegram messages: grouping, repeat_interval and inhibition are outside replay.
"""

import argparse
import ast
import hashlib
import itertools
import json
import math
import operator
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONITORING = ROOT / 'backend/charts/monitoring'
INVENTORY = MONITORING / 'metric-inventory.prod.json'
PROXY = '/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy'
REF = re.compile(r'\$\{?([A-Za-z][A-Za-z0-9_]*)\}?')


class Unsupported(ValueError):
    pass


def seconds(value):
    if isinstance(value, (int, float)):
        return float(value)
    parts = re.findall(r'(\d+(?:\.\d+)?)([smhdw])', value)
    if not parts or ''.join(n + u for n, u in parts) != value:
        raise ValueError(f'invalid duration: {value}')
    return sum(float(n) * dict(s=1, m=60, h=3600, d=86400, w=604800)[u] for n, u in parts)


def rules(paths=None):
    found = {}
    for path in paths or sorted((MONITORING / 'alerts').glob('*.json')):
        for rule in json.loads(Path(path).read_text()):
            if rule['uid'] in found:
                raise ValueError(f"duplicate UID: {rule['uid']}")
            found[rule['uid']] = rule
    return found


def prometheus(node):
    return node['model'].get('datasource', {}).get('type') == 'prometheus' or node.get('datasourceUid') == 'prometheus'


def metric_names(expr):
    """Tokenize selectors, stripping strings, labels, functions and durations."""
    names = set(re.findall(r'__name__\s*=\s*"([A-Za-z_:][A-Za-z0-9_:]*)"', expr))
    if re.search(r'__name__\s*(?:=~|!~|!=)', expr):
        raise Unsupported('regex/negative metric-name selector needs explicit inventory review')
    clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', expr)
    clean = re.sub(r'\{[^}]*\}|\[[^]]*\]', '', clean)
    clean = re.sub(r'\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)', '', clean)
    skip = {'and', 'or', 'unless', 'bool', 'offset', 'by', 'without', 'on', 'ignoring'}
    for match in re.finditer(r'(?<![\w.])([A-Za-z_:][A-Za-z0-9_:]*)', clean):
        word = match.group(1)
        if word not in skip and not clean[match.end() :].lstrip().startswith('('):
            names.add(word)
    return names


# Only the fields that decide whether and when a rule fires. Notification routing, annotations
# and labels change independently (e.g. a fleet-wide timing policy) and must not void debt baselines.
FINGERPRINT_FIELDS = ('condition', 'data', 'for', 'noDataState', 'execErrState')


def fingerprint(rule):
    semantic = {key: rule.get(key) for key in FINGERPRINT_FIELDS}
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Prometheus:
    def __init__(self, url=None, context=None):
        self.url, self.context = url, context
        self.cache = {}

    def get(self, endpoint, **params):
        path = '/api/v1/' + endpoint + '?' + urllib.parse.urlencode(params)
        if path in self.cache:
            return self.cache[path]
        try:
            if self.url:
                with urllib.request.urlopen(self.url.rstrip('/') + path, timeout=120) as response:
                    data = json.load(response)
            else:
                result = subprocess.run(
                    ['kubectl', '--context', self.context, 'get', '--raw', PROXY + path],
                    capture_output=True,
                    text=True,
                    timeout=150,
                )
                if result.returncode:
                    # Classify only known phrases; stderr can contain credentials.
                    message = (result.stderr + result.stdout).lower()
                    category = next(
                        (
                            label
                            for phrase, label in (
                                ('too many samples', 'sample budget exceeded'),
                                ('timeout', 'request timeout'),
                                ('deadline', 'request timeout'),
                                ('forbidden', 'authorization failed'),
                                ('unauthorized', 'authorization failed'),
                                ('badrequest', 'query rejected'),
                            )
                            if phrase in message
                        ),
                        'kube proxy request failed',
                    )
                    raise RuntimeError(category)
                data = json.loads(result.stdout)
            if data.get('status') != 'success' or data.get('warnings'):
                raise RuntimeError('Prometheus failed or returned partial/warned results')
            if len(self.cache) > 128:
                self.cache.clear()
            self.cache[path] = data['data']
            return data['data']
        except (subprocess.TimeoutExpired, OSError) as error:
            raise RuntimeError(f'Prometheus transport failed: {type(error).__name__}') from None

    def range(self, query, start, end, step):
        # Exact grid, daily chunks: avoid ten-day counter scans timing out.
        series = {}
        cursor = start
        while cursor <= end:
            stop = min(end, cursor + max(1, 86400 // step - 1) * step)
            for item in self.get('query_range', query=query, start=cursor, end=stop, step=step)['result']:
                key = tuple(sorted(item['metric'].items()))
                series.setdefault(key, {'metric': item['metric'], 'values': []})['values'].extend(item['values'])
            cursor = stop + step
        return list(series.values())


def threshold(value, evaluator):
    if not math.isfinite(value):
        return math.nan
    kind, p = evaluator['type'], evaluator['params']
    ops = dict(gt=operator.gt, lt=operator.lt, gte=operator.ge, lte=operator.le, eq=operator.eq, ne=operator.ne)
    if kind in ops and len(p) in (1, 2):
        return float(ops[kind](value, p[0]))
    if kind in ('within_range', 'outside_range') and len(p) == 2:
        inside = p[0] < value < p[1]
        return float(inside if kind == 'within_range' else not inside)
    raise Unsupported(f'unsupported evaluator {kind}')


def reduce_values(values, kind, settings=None):
    settings = settings or {}
    mode = settings.get('mode', 'strict')
    if mode not in ('strict', 'dropNN', 'replaceNN'):
        raise Unsupported(f'unknown reduce mode {mode}')
    if mode == 'dropNN':
        values = [v for v in values if math.isfinite(v)]
    elif mode == 'replaceNN':
        values = [v if math.isfinite(v) else settings['replaceWithValue'] for v in values]
    if kind == 'count':
        return float(len(values))
    if mode == 'strict' and any(not math.isfinite(v) for v in values):
        return math.nan
    if not values:
        return 0.0 if kind == 'sum' else math.nan
    funcs = {'last': lambda v: v[-1], 'sum': sum, 'min': min, 'max': max, 'mean': lambda v: sum(v) / len(v)}
    if kind not in funcs:
        raise Unsupported(f'unknown reducer {kind}')
    return funcs[kind](values)


def math_expression(expression, inputs):
    """AST interpreter: no eval, attribute access or arbitrary Python calls."""
    source = REF.sub(r'\1', expression).replace('&&', ' and ').replace('||', ' or ')
    source = re.sub(r'!(?!=)', ' not ', source).strip()
    tree = ast.parse(source, mode='eval').body
    binary = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    compare = {
        ast.Gt: operator.gt,
        ast.Lt: operator.lt,
        ast.GtE: operator.ge,
        ast.LtE: operator.le,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
    }
    funcs = {
        'abs': abs,
        'log': math.log,
        'ceil': math.ceil,
        'floor': math.floor,
        'round': round,
        'is_nan': math.isnan,
        'is_inf': math.isinf,
        'is_number': math.isfinite,
    }

    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name) and node.id in inputs:
            return inputs[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return binary[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in compare:
            return float(compare[type(node.ops[0])](walk(node.left), walk(node.comparators[0])))
        if isinstance(node, ast.BoolOp):
            values = [walk(v) != 0 for v in node.values]
            return float(all(values) if isinstance(node.op, ast.And) else any(values))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            value = walk(node.operand)
            return (
                -value
                if isinstance(node.op, ast.USub)
                else (float(not value) if isinstance(node.op, ast.Not) else value)
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in funcs
            and len(node.args) == 1
            and not node.keywords
        ):
            return funcs[node.func.id](walk(node.args[0]))
        raise Unsupported('unsupported math syntax')

    try:
        return float(walk(tree))
    except (ZeroDivisionError, OverflowError, ValueError) as error:
        if isinstance(error, Unsupported):
            raise
        return math.nan


def joined_math(expression, inputs):
    refs = list(dict.fromkeys(REF.findall(expression)))
    if not refs:
        return {(): [math_expression(expression, {})]}
    for ref in refs:
        keys = {tuple(k for k, _ in labels) for labels in inputs[ref]}
        if len(keys) > 1:
            raise Unsupported('heterogeneous label keys: Grafana join is undefined')
    output = {}
    for combination in itertools.product(*(inputs[ref].items() for ref in refs)):
        labels = {}
        valid = True
        for i, (key, _) in enumerate(combination):
            current = dict(key)
            for j in range(i):
                previous = dict(combination[j][0])
                singleton = len(inputs[refs[i]]) == len(inputs[refs[j]]) == 1
                if not singleton and not (current.items() <= previous.items() or previous.items() <= current.items()):
                    valid = False
            labels.update(current)
        if not valid:
            continue
        lengths = {len(values) for _, values in combination}
        if len(lengths) != 1:
            raise Unsupported('math mixes range frames and numbers; resample/reduce first')
        key = tuple(sorted(labels.items()))
        if key in output:
            raise Unsupported('ambiguous many-to-many join')
        output[key] = [
            math_expression(expression, dict(zip(refs, values))) for values in zip(*(v for _, v in combination))
        ]
    return output


def evaluate(rule, query_frames):
    values = dict(query_frames)
    pending = {d['refId']: d['model'] for d in rule['data'] if d['refId'] not in values}
    while pending:
        progressed = False
        for ref, model in list(pending.items()):
            kind = model.get('type')
            refs = REF.findall(model.get('expression', '')) if kind == 'math' else [model.get('expression')]
            if kind == 'classic_conditions':
                refs = [c['query']['params'][0] for c in model['conditions']]
            if not all(r in values for r in refs):
                continue
            if kind == 'reduce':
                values[ref] = {
                    k: [reduce_values(v, model['reducer'], model.get('settings'))] for k, v in values[refs[0]].items()
                }
            elif kind == 'math':
                values[ref] = joined_math(model['expression'], values)
            elif kind == 'threshold':
                if len(model['conditions']) != 1 or model.get('unloadEvaluator'):
                    raise Unsupported('multiple thresholds/recovery hysteresis')
                values[ref] = {
                    k: [threshold(v, model['conditions'][0]['evaluator']) for v in seq]
                    for k, seq in values[refs[0]].items()
                }
            elif kind == 'classic_conditions':
                result = None
                for condition in model['conditions']:
                    frame = values[condition['query']['params'][0]]
                    hits = [
                        threshold(reduce_values(v, condition['reducer']['type']), condition['evaluator'])
                        for v in frame.values()
                    ]
                    if not hits:
                        result = None
                        break
                    hit = any(hits)
                    op = condition['operator']['type']
                    if op not in ('and', 'or'):
                        raise Unsupported(f'classic operator {op}')
                    result = hit if result is None else (result and hit if op == 'and' else result or hit)
                values[ref] = {} if result is None else {(): [float(result)]}
            else:
                raise Unsupported(f'unsupported expression node {kind}')
            del pending[ref]
            progressed = True
        if not progressed:
            raise Unsupported('unresolved/cyclic expression dependencies')
    frame = values[rule['condition']]
    if any(len(v) != 1 for v in frame.values()):
        raise Unsupported('condition must reduce to one number per label set')
    if any(not frame for frame in query_frames.values()):
        return {}
    return {k: v[0] for k, v in frame.items()}


def episodes(rule, samples, start, end, step):
    pending, active, durations = {}, {}, []
    firing_ticks = 0
    unknown = 0
    for timestamp, frame in samples:
        if not frame or all(not math.isfinite(v) for v in frame.values()):
            state = rule.get('noDataState', 'NoData')
            if state == 'Alerting':
                frame = {key: 1.0 for key in (set(pending) | set(active) or {('__no_data__',)})}
            elif state == 'KeepLast':
                unknown += 1
                firing_ticks += bool(active)
                continue
            else:
                unknown += state != 'OK'
                frame = {}
        for key in set(pending) | set(active) | set(frame):
            hit = math.isfinite(frame.get(key, math.nan)) and frame[key] != 0
            if hit:
                pending.setdefault(key, timestamp)
                if timestamp - pending[key] >= seconds(rule['for']):
                    active.setdefault(key, timestamp)
            else:
                pending.pop(key, None)
                if key in active:
                    durations.append(timestamp - active.pop(key))
        firing_ticks += bool(active)
    durations.extend(end + step - since for since in active.values())
    span = end + step - start
    flap = sum(d <= max(2 * step, 600) for d in durations) >= 10
    return dict(
        episodes=len(durations),
        total_duration_seconds=sum(durations),
        longest_seconds=max(durations, default=0),
        percent_time_firing=round(100 * firing_ticks * step / span, 3),
        would_page_per_week=round(len(durations) * 604800 / span, 3),
        never_fired=not durations,
        flap=flap,
        unknown_ticks=unknown,
        open_episodes=len(active),
    )


def replay(rule, client, start, end, step):
    queries = [d for d in rule['data'] if d.get('datasourceUid') not in ('__expr__', '-100')]
    if any(not prometheus(d) for d in queries):
        raise Unsupported('non-Prometheus datasource: separate aggregate evidence required')
    history, metric_counts, selectors, query_series = {}, {}, {}, {}
    for node in queries:
        model = node['model']
        for name in metric_names(model['expr']):
            result = client.get('query', query=f'count({{__name__="{name}"}})', time=end)['result']
            metric_counts[name] = int(float(result[0]['value'][1])) if result else 0
        for name in metric_names(model['expr']):
            matches = re.findall(r'\b' + re.escape(name) + r'(\s*\{[^}]*\})?', model['expr'])
            for labels in matches:
                selector = name + labels.strip()
                result = client.get('query', query=f'count({selector})', time=end)['result']
                selectors[selector] = int(float(result[0]['value'][1])) if result else 0
        if not model.get('instant'):
            window = node['relativeTimeRange']
            resolution = max(
                1,
                math.ceil(model.get('intervalMs', 1000) / 1000),
                math.ceil((window['from'] - window['to']) / model.get('maxDataPoints', 43200)),
            )
            if (window['from'] - window['to']) / resolution > 11000:
                raise Unsupported('range frame exceeds 11000-point request budget')
            ticks = {}
            for tick in range(start, end + 1, step):
                result = client.get(
                    'query_range',
                    query=model['expr'],
                    start=tick - window['from'],
                    end=tick - window['to'],
                    step=resolution,
                )['result']
                ticks[tick] = {
                    tuple(sorted((k, v) for k, v in series['metric'].items() if k != '__name__')): [
                        float(v) for _, v in series['values']
                    ]
                    for series in result
                }
            history[node['refId']] = ticks
            continue
        offset = node.get('relativeTimeRange', {}).get('to', 0)
        result = client.range(model['expr'], start - offset, end - offset, step)
        query_series[node['refId']] = len(result)
        ticks = {}
        for series in result:
            labels = tuple(sorted((k, v) for k, v in series['metric'].items() if k != '__name__'))
            for timestamp, value in series['values']:
                ticks.setdefault(int(timestamp) + offset, {})[labels] = [float(value)]
        history[node['refId']] = ticks
    samples = (
        (t, evaluate(rule, {ref: ticks.get(t, {}) for ref, ticks in history.items()}))
        for t in range(start, end + 1, step)
    )
    result = episodes(rule, samples, start, end, step)
    result.update(
        metrics=metric_counts,
        selectors=selectors,
        query_series=query_series,
        metric_exists=bool(metric_counts) and all(metric_counts.values()),
        series_count=sum(metric_counts.values()),
        queries={d['refId']: d['model']['expr'] for d in queries},
    )
    result['verdict'] = (
        'dead-metric'
        if not result['metric_exists']
        else (
            'needs-human'
            if result['unknown_ticks']
            else (
                'mistuned-noisy'
                if result['percent_time_firing'] > 5 or result['flap']
                else 'never-fires' if result['never_fired'] else 'ok'
            )
        )
    )
    return result


def lint_rule(rule, inventory):
    errors = []
    refs = [d['refId'] for d in rule['data']]
    if len(refs) != len(set(refs)) or rule['condition'] not in refs:
        errors.append('duplicate refs or missing condition')
    seconds(rule['for'])
    if rule.get('noDataState') not in ('OK', 'NoData', 'Alerting', 'KeepLast'):
        errors.append('unknown noDataState')
    for node in rule['data']:
        model = node['model']
        if prometheus(node):
            # The observed snapshot remains historical production evidence.
            # Declared metrics let a source-backed exporter add alert contracts
            # before deployment without pretending its series were observed.
            known_metrics = set(inventory['metrics']) | set(inventory.get('declared_metrics', []))
            missing = metric_names(model['expr']) - known_metrics
            if missing:
                errors.append('missing metrics: ' + ', '.join(sorted(missing)))
            if seconds(rule['for']) == 0 and re.search(r'\brate\(|/|\bavg\(', model['expr']):
                errors.append('no pending duration on noisy rate/ratio/average')
        elif node.get('datasourceUid') in ('__expr__', '-100'):
            kind = model.get('type')
            dependencies = REF.findall(model.get('expression', '')) if kind == 'math' else [model.get('expression')]
            if kind == 'classic_conditions':
                dependencies = [c['query']['params'][0] for c in model['conditions']]
            if kind not in ('math', 'reduce', 'threshold', 'classic_conditions'):
                errors.append(f'unsupported node: {kind}')
            if any(ref not in refs for ref in dependencies):
                errors.append('missing dependency')
            if kind == 'math':
                math_expression(model['expression'], {ref: 1 for ref in dependencies})
            if kind == 'threshold':
                for condition in model['conditions']:
                    ev = condition['evaluator']
                    try:
                        threshold(0, ev)
                    except Unsupported as error:
                        errors.append(str(error))
                    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in ev['params']):
                        errors.append('non-finite threshold')
                    # A boolean expression's threshold must be in the boolean domain.
                    source = next((d['model'] for d in rule['data'] if d['refId'] == model['expression']), {})
                    if source.get('type') == 'math' and re.search(r'[<>=]|&&|\|\|', source.get('expression', '')):
                        if any(v < 0 or v > 1 for v in ev['params']):
                            errors.append('boolean threshold outside [0,1]')
    try:
        evaluate(rule, {d['refId']: {} for d in rule['data'] if d.get('datasourceUid') not in ('__expr__', '-100')})
    except (Unsupported, KeyError, SyntaxError) as error:
        errors.append(str(error))
    return sorted(set(errors))


def lint(all_rules, inventory):
    failures, debt = {}, {}
    for uid, rule in all_rules.items():
        try:
            errors = lint_rule(rule, inventory)
        except (ValueError, KeyError, TypeError, SyntaxError) as error:
            errors = [str(error)]
        if uid in inventory.get('admission_holds', {}) and not rule.get('isPaused'):
            errors.append('admission hold must remain paused: ' + inventory['admission_holds'][uid])
        if errors:
            baseline = inventory.get('legacy_debt', {}).get(uid, {})
            if baseline.get('sha256') == fingerprint(rule) and baseline.get('errors') == errors:
                debt[uid] = errors
            else:
                failures[uid] = errors
    return dict(failures=failures, legacy_debt=debt)


def markdown(results):
    lines = ['| UID | Metric series | Episodes | Firing % | Pages/week* | Verdict |', '|---|---:|---:|---:|---:|---|']
    for r in results:
        lines.append(
            f"| {r['uid']} | {r.get('series_count', '—')} | {r.get('episodes', '—')} | "
            f"{r.get('percent_time_firing', '—')} | {r.get('would_page_per_week', '—')} | {r['verdict']} |"
        )
    return '\n'.join(lines) + '\n\n*Instance starts only; notification grouping/repeats are not simulated.\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rules', nargs='+', type=Path)
    parser.add_argument('--uids', nargs='+')
    parser.add_argument('--lint', action='store_true')
    parser.add_argument('--inventory', type=Path, default=INVENTORY)
    parser.add_argument('--refresh-inventory', action='store_true')
    connection = parser.add_mutually_exclusive_group()
    connection.add_argument('--prom-url')
    connection.add_argument('--kube-context')
    parser.add_argument('--days', type=float, default=10)
    parser.add_argument('--step', type=int)
    parser.add_argument('--json-output', type=Path)
    parser.add_argument('--markdown-output', type=Path)
    args = parser.parse_args()
    selected = rules(args.rules)
    if args.uids:
        unknown = set(args.uids) - set(selected)
        if unknown:
            parser.error('unknown UIDs: ' + ', '.join(sorted(unknown)))
        selected = {uid: selected[uid] for uid in args.uids}
    if args.lint:
        result = lint(selected, json.loads(args.inventory.read_text()))
        print(json.dumps(result, indent=2))
        return bool(result['failures'])
    if not (args.prom_url or args.kube_context):
        parser.error('live reads require --prom-url or explicit --kube-context')
    if not 0 < args.days <= 10 or (args.step is not None and args.step < 60):
        parser.error('window must be (0,10] days and step >=60s')
    client = Prometheus(args.prom_url, args.kube_context)
    end = int(time.time())
    if args.refresh_inventory:
        metrics = client.get('label/__name__/values', start=end - 10 * 86400, end=end)
        old = json.loads(args.inventory.read_text()) if args.inventory.exists() else {}
        args.inventory.write_text(
            json.dumps(
                dict(
                    captured_at=end,
                    window_days=10,
                    metrics=sorted(metrics),
                    declared_metrics=old.get('declared_metrics', []),
                    legacy_debt=old.get('legacy_debt', {}),
                    admission_holds=old.get('admission_holds', {}),
                ),
                indent=2,
            )
            + '\n'
        )
        return 0
    # First retained sample, not TSDB head minTime (which covers only the head).
    available = client.get(
        'query_range', query='min(timestamp(up))', start=end - int(args.days * 86400), end=end, step=3600
    )['result']
    first = min((int(t) for s in available for t, _ in s['values']), default=end)
    output = []
    for uid, rule in selected.items():
        step = args.step or int(seconds(rule.get('interval', '5m')))
        step = max(step, 60)
        start, stop = math.ceil(first / step) * step, end // step * step
        lookback = max(
            (
                seconds(m)
                for d in rule['data']
                for m in re.findall(r'\[(\d+[smhdw])(?::[^]]*)?\]', d['model'].get('expr', ''))
            ),
            default=0,
        )
        result = dict(
            uid=uid,
            start=start,
            end=stop,
            step=step,
            lookback_seconds=lookback,
            incomplete_lookback_until=start + lookback,
            definition_sha256=fingerprint(rule),
        )
        try:
            if start >= stop:
                raise Unsupported('insufficient retained history')
            result.update(replay(rule, client, start, stop, step))
        except (Unsupported, RuntimeError, KeyError, ValueError) as error:
            result.update(verdict='needs-human', reason=str(error))
        output.append(result)
        if args.json_output:
            args.json_output.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
        print(f"{uid}: {result['verdict']}", flush=True)
    if args.json_output:
        args.json_output.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    if args.markdown_output:
        args.markdown_output.write_text(markdown(output))
    print(markdown(output))
    return int(any(r['verdict'] in ('dead-metric', 'mistuned-noisy', 'needs-human') for r in output))


if __name__ == '__main__':
    raise SystemExit(main())
