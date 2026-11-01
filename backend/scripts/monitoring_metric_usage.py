"""Conservative metric consumer inventory; no production IO.

Use with a JSON array of metric names (or Prometheus label-values response).
Results map each observed metric to committed consumers. This intentionally
matches comments as well as queries: a false positive prevents a risky drop.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IDENTIFIER = re.compile(r'[a-zA-Z_:][a-zA-Z0-9_:]*')
NAME_SELECTOR = re.compile(r'__name__\s*(=~|=)\s*"([^"\n]*)"')
QUERY_READER = re.compile(r'api/v1/query|query_prometheus|prometheus_url|prom_query')


def consumer_files(repo: Path = REPO) -> list[Path]:
    """Find dashboards, rules, autoscaling queries, and code reading Prometheus."""
    tracked = (
        subprocess.check_output(
            [
                'git',
                'ls-files',
                '-z',
                '--',
                '*dashboard*',
                '*alert*',
                '*prometheus-adapter*',
                '*recording*',
                '*/prometheus/rules*',
            ],
            cwd=repo,
        )
        .decode()
        .split('\0')
    )
    # Git's native scanner avoids reading thousands of unrelated source files in
    # Python. Include inline recording rules anywhere, not just the main chart.
    for pattern, globs in (
        (QUERY_READER.pattern, ['*.py', '*.sh', '*.ts', '*.js']),
        (r'^[[:space:]]*(expr|metricsQuery|seriesQuery):', ['*.yaml', '*.yml']),
    ):
        result = subprocess.run(
            ['git', 'grep', '-l', '-z', '-I', '-E', pattern, '--', *globs], cwd=repo, capture_output=True
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.decode())
        tracked.extend(result.stdout.decode().split('\0'))
    result = []
    for name in sorted(set(tracked)):
        path = repo / name
        if (
            path.suffix not in {'.json', '.yaml', '.yml', '.py', '.sh', '.ts', '.js'}
            or '/tests/' in name
            or name.startswith('backend/scripts/monitoring_metric_usage')
        ):
            continue
        if path.is_file():
            result.append(path)
    return result


def consumer_text(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    # Decode JSON strings so metric-name selectors are checked, not their escapes.
    if path.suffix == '.json':
        return '\n'.join(_strings(json.loads(text)))
    # Vendored Helm dashboards embed escaped JSON in YAML templates.
    return text.replace('\\"', '"')


def _strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def referenced_metrics(text: str, names: set[str]) -> set[str]:
    if len(names) < 100:
        matches = {
            name
            for name in names
            if name in text and re.search(r'(?<![a-zA-Z0-9_:])' + re.escape(name) + r'(?![a-zA-Z0-9_:])', text)
        }
    else:
        matches = names.intersection(IDENTIFIER.findall(text))
    for operator, selector in NAME_SELECTOR.findall(text):
        if operator == '=~':
            matches.update(name for name in names if re.fullmatch(selector, name))
        elif selector in names:
            matches.add(selector)
    return matches


def usage_map(names: set[str], paths: list[Path], repo: Path = REPO) -> dict[str, list[str]]:
    usage = {name: [] for name in sorted(names)}
    for path in paths:
        for name in referenced_metrics(consumer_text(path), names):
            usage[name].append(str(path.relative_to(repo)))
    return usage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics-file', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.metrics_file.read_text())
    names = set(data['data'] if isinstance(data, dict) else data)
    print(json.dumps(usage_map(names, consumer_files()), indent=2))


if __name__ == '__main__':
    main()
