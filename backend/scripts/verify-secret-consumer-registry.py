#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / 'backend/deploy/secret_consumer_registry.yaml'

SECRET_ASSIGNMENT_RE = re.compile(r'\b([A-Z][A-Z0-9_]*)=([A-Z][A-Z0-9_]*):(?:latest|\d+)\b')
SHELL_ENV_RE = re.compile(
    r'\$[{]?([A-Z][A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIALS|SERVICE_ACCOUNT|P12|ADMIN_KEY)[A-Z0-9_]*)[}]?'
)
GITHUB_SECRET_RE = re.compile(r'\bsecrets\.([A-Z][A-Z0-9_]*)\b')
GITHUB_DYNAMIC_SECRET_RE = re.compile(r'\bsecrets\s*\[')
GITHUB_INHERIT_RE = re.compile(r'(?m)^\s*secrets:\s*inherit\s*$')
CHART_SECRET_KEY_RE = re.compile(
    r'secretKeyRef:\s*(?:\n\s+[A-Za-z]+:\s*[^\n]+){0,4}\n\s+key:\s*["\']?([A-Za-z][A-Za-z0-9_]*)'
)
SOURCE_ENV_RE = re.compile(r'''(?x)
    (?:
        os\.(?:getenv|environ\.get)\(\s*["']([A-Z][A-Z0-9_]*)["']
        | os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]
        | process\.env\.([A-Z][A-Z0-9_]*)
        | process\.env\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]
    )
    ''')


@dataclass(frozen=True)
class Consumer:
    secret: str
    runtime: str
    service: str
    environment: str
    env_name: str
    source: str


@dataclass(frozen=True)
class RegistryIssue:
    severity: str
    secret: str
    message: str
    source: str = ''


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Verify high-risk secret registry coverage without reading or printing secret values.'
    )
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    parser.add_argument(
        '--warnings-as-errors',
        action='store_true',
        help='Treat registered-but-undiscovered secrets as errors.',
    )
    args = parser.parse_args()

    report = build_report(root=args.root, registry_path=args.registry)
    if args.warnings_as_errors:
        report['issues'].extend(
            {'severity': 'ERROR', 'secret': issue['secret'], 'message': issue['message'], 'source': issue['source']}
            for issue in report['warnings']
        )
        report['warnings'] = []
        report['status'] = 'FAIL' if report['issues'] else 'PASS'

    if args.format == 'json':
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    return 1 if report['status'] == 'FAIL' else 0


def build_report(*, root: Path, registry_path: Path) -> dict[str, Any]:
    registry = _load_yaml(registry_path)
    schema_issues = _validate_registry_schema(registry)
    registry_dir = registry_path.parent
    secret_entries = registry.get('secrets', {})
    if not isinstance(secret_entries, dict):
        secret_entries = {}
    registered = set(secret_entries)
    ignored = set(_string_list(registry.get('ignored_secret_names', [])))
    high_risk_patterns = _compile_valid_patterns(registry.get('high_risk_name_patterns', []))
    refresh_methods = registry.get('runtime_refresh_methods', {})
    if not isinstance(refresh_methods, dict):
        refresh_methods = {}

    consumers = discover_consumers(root=root, registry_names=registered)
    deploy_consumers = [consumer for consumer in consumers if consumer.runtime != 'code_reference']
    discovered_names = {consumer.secret for consumer in consumers}

    issues: list[RegistryIssue] = list(schema_issues)
    warnings: list[RegistryIssue] = []
    issues.extend(_discover_unscannable_secret_references(root))
    for consumer in sorted(deploy_consumers, key=lambda item: (item.secret, item.source, item.service)):
        if consumer.secret in ignored or consumer.secret in registered:
            continue
        issues.append(
            RegistryIssue(
                severity='ERROR',
                secret=consumer.secret,
                message='secret-bearing deploy reference is missing from secret_consumer_registry.yaml or ignored_secret_names',
                source=consumer.source,
            )
        )

    for consumer in sorted(
        [consumer for consumer in consumers if consumer.runtime == 'code_reference'],
        key=lambda item: (item.secret, item.source, item.service),
    ):
        if consumer.secret in ignored or consumer.secret in registered:
            continue
        if _is_high_risk_name(consumer.secret, high_risk_patterns):
            issues.append(
                RegistryIssue(
                    severity='ERROR',
                    secret=consumer.secret,
                    message='high-risk source env reference is missing from secret_consumer_registry.yaml',
                    source=consumer.source,
                )
            )

    for secret in sorted(registered - discovered_names):
        entry = secret_entries.get(secret, {})
        if isinstance(entry, dict) and entry.get('status') in {'code_only', 'expected_absent'}:
            continue
        warnings.append(
            RegistryIssue(
                severity='WARN',
                secret=secret,
                message='registered secret was not discovered in checked deploy/runtime surfaces',
            )
        )

    issue_names = {issue.secret for issue in issues}
    reported_consumers = [
        consumer for consumer in consumers if consumer.secret in registered or consumer.secret in issue_names
    ]

    return {
        'status': 'FAIL' if issues else 'PASS',
        'registry': _relative(root, registry_path),
        'registered_secret_count': len(registered),
        'consumer_count': len(deploy_consumers),
        'consumers': [
            _consumer_record(consumer, secret_entries, refresh_methods)
            for consumer in sorted(reported_consumers, key=_consumer_sort_key)
        ],
        'issues': [asdict(issue) for issue in issues],
        'warnings': [asdict(issue) for issue in warnings],
        'schema_version': registry.get('schema_version'),
        'registry_dir': _relative(root, registry_dir),
    }


def discover_consumers(*, root: Path, registry_names: set[str]) -> list[Consumer]:
    consumers: list[Consumer] = []
    consumers.extend(_discover_runtime_manifest_consumers(root))
    consumers.extend(_discover_chart_consumers(root))
    consumers.extend(_discover_chart_text_consumers(root))
    consumers.extend(_discover_text_secret_bindings(root))
    consumers.extend(_discover_registered_code_references(root, registry_names))
    consumers.extend(_discover_source_env_references(root))
    return _dedupe_consumers(consumers)


def _discover_runtime_manifest_consumers(root: Path) -> list[Consumer]:
    path = root / 'backend/deploy/runtime_env.yaml'
    if not path.exists():
        return []
    manifest = _load_yaml(path)
    environments = manifest.get('environments', {})
    if not isinstance(environments, dict):
        return []

    consumers: list[Consumer] = []
    for environment, env_config in environments.items():
        if not isinstance(env_config, dict):
            continue
        gke = env_config.get('gke', {})
        if isinstance(gke, dict):
            for service, service_config in gke.items():
                if not isinstance(service_config, dict):
                    continue
                for env_name, entry in _mapping_items(service_config.get('env', {})):
                    secret_entry = entry.get('secret') if isinstance(entry, dict) else None
                    if not isinstance(secret_entry, dict):
                        continue
                    secret = secret_entry.get('key')
                    if isinstance(secret, str):
                        consumers.append(
                            Consumer(
                                secret=secret,
                                runtime='gke',
                                service=str(service),
                                environment=str(environment),
                                env_name=str(env_name),
                                source=_relative(root, path),
                            )
                        )
        cloud_run_config = env_config.get('cloud_run', {})
        cloud_run = cloud_run_config.get('services', {}) if isinstance(cloud_run_config, dict) else {}
        if isinstance(cloud_run, dict):
            for service, service_config in cloud_run.items():
                if not isinstance(service_config, dict):
                    continue
                for env_name, entry in _mapping_items(service_config.get('secrets', {})):
                    secret = entry.get('secret') if isinstance(entry, dict) else None
                    if isinstance(secret, str):
                        consumers.append(
                            Consumer(
                                secret=secret,
                                runtime='cloud_run',
                                service=str(service),
                                environment=str(environment),
                                env_name=str(env_name),
                                source=_relative(root, path),
                            )
                        )
    return consumers


def _discover_chart_consumers(root: Path) -> list[Consumer]:
    charts_dir = root / 'backend/charts'
    if not charts_dir.exists():
        return []

    consumers: list[Consumer] = []
    for path in sorted(charts_dir.rglob('*.yaml')):
        if '/charts/' in path.as_posix().removeprefix(charts_dir.as_posix()):
            continue
        if '/samples/' in path.as_posix():
            continue
        loaded = _load_yaml_or_none(path)
        if not isinstance(loaded, dict):
            continue
        env_entries = loaded.get('env')
        if not isinstance(env_entries, list):
            continue
        chart_name = _chart_name(charts_dir, path)
        environment = _environment_from_filename(path.name)
        for entry in env_entries:
            if not isinstance(entry, dict):
                continue
            env_name = entry.get('name')
            if not isinstance(env_name, str):
                continue
            secret = _secret_key_from_env_entry(entry)
            if secret is None:
                continue
            consumers.append(
                Consumer(
                    secret=secret,
                    runtime='gke',
                    service=chart_name,
                    environment=environment,
                    env_name=env_name,
                    source=_relative(root, path),
                )
            )
    return consumers


def _discover_chart_text_consumers(root: Path) -> list[Consumer]:
    charts_dir = root / 'backend/charts'
    if not charts_dir.exists():
        return []

    consumers: list[Consumer] = []
    for path in sorted(charts_dir.rglob('*.yaml')):
        if '/charts/' in path.as_posix().removeprefix(charts_dir.as_posix()):
            continue
        if '/samples/' in path.as_posix():
            continue
        text = _read_text(path)
        chart_name = _chart_name(charts_dir, path)
        environment = _environment_from_filename(path.name)
        for secret in CHART_SECRET_KEY_RE.findall(text):
            consumers.append(
                Consumer(
                    secret=secret,
                    runtime='gke',
                    service=chart_name,
                    environment=environment,
                    env_name=secret,
                    source=_relative(root, path),
                )
            )
    return consumers


def _discover_text_secret_bindings(root: Path) -> list[Consumer]:
    consumers: list[Consumer] = []
    workflow_dir = root / '.github/workflows'
    for path in sorted(workflow_dir.glob('*.yml')) + sorted(workflow_dir.glob('*.yaml')):
        text = _read_text(path)
        service = path.stem
        for env_name, secret in SECRET_ASSIGNMENT_RE.findall(text):
            consumers.append(
                Consumer(
                    secret=secret,
                    runtime='github_actions',
                    service=service,
                    environment='workflow',
                    env_name=env_name,
                    source=_relative(root, path),
                )
            )
        for secret in GITHUB_SECRET_RE.findall(text):
            consumers.append(
                Consumer(
                    secret=secret,
                    runtime='github_actions',
                    service=service,
                    environment='workflow',
                    env_name=secret,
                    source=_relative(root, path),
                )
            )

    codemagic = root / 'codemagic.yaml'
    if codemagic.exists():
        text = _read_text(codemagic)
        for secret in SHELL_ENV_RE.findall(text):
            consumers.append(
                Consumer(
                    secret=secret,
                    runtime='codemagic',
                    service='codemagic',
                    environment='workflow',
                    env_name=secret,
                    source=_relative(root, codemagic),
                )
            )
    return consumers


def _discover_unscannable_secret_references(root: Path) -> list[RegistryIssue]:
    issues: list[RegistryIssue] = []
    workflow_dir = root / '.github/workflows'
    for path in sorted(workflow_dir.glob('*.yml')) + sorted(workflow_dir.glob('*.yaml')):
        text = _read_text(path)
        source = _relative(root, path)
        if GITHUB_INHERIT_RE.search(text):
            issues.append(
                RegistryIssue(
                    severity='ERROR',
                    secret='secrets: inherit',
                    message='workflow inherits an unenumerated secret set; enumerate secrets or add a verifier exception',
                    source=source,
                )
            )
        if GITHUB_DYNAMIC_SECRET_RE.search(text):
            issues.append(
                RegistryIssue(
                    severity='ERROR',
                    secret='secrets[...]',
                    message='workflow uses dynamic secret lookup; enumerate possible secret names for registry coverage',
                    source=source,
                )
            )
    return issues


def _discover_registered_code_references(root: Path, registry_names: set[str]) -> list[Consumer]:
    registry_env_names = {name for name in registry_names if re.fullmatch(r'[A-Z][A-Z0-9_]*', name)}
    if not registry_env_names:
        return []
    consumers: list[Consumer] = []
    patterns = {name: re.compile(rf'["\']{re.escape(name)}["\']') for name in registry_env_names}
    search_roots = [root / 'backend', root / 'scripts']
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for path in sorted(search_root.rglob('*.py')):
            if '.venv' in path.parts or '__pycache__' in path.parts:
                continue
            text = _read_text(path)
            for name, pattern in patterns.items():
                if pattern.search(text):
                    consumers.append(
                        Consumer(
                            secret=name,
                            runtime='code_reference',
                            service='source',
                            environment='checked_in_code',
                            env_name=name,
                            source=_relative(root, path),
                        )
                    )
    return consumers


def _discover_source_env_references(root: Path) -> list[Consumer]:
    consumers: list[Consumer] = []
    search_roots = [root / 'backend', root / 'scripts', root / 'web']
    suffixes = {'.py', '.ts', '.tsx', '.js', '.jsx'}
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for path in sorted(search_root.rglob('*')):
            if path.suffix not in suffixes:
                continue
            if any(part in {'.venv', '__pycache__', 'node_modules', 'build', 'dist'} for part in path.parts):
                continue
            text = _read_text(path)
            for match in SOURCE_ENV_RE.findall(text):
                name = next((group for group in match if group), '')
                if not name:
                    continue
                consumers.append(
                    Consumer(
                        secret=name,
                        runtime='code_reference',
                        service='source',
                        environment='checked_in_code',
                        env_name=name,
                        source=_relative(root, path),
                    )
                )
    return consumers


def _validate_registry_schema(registry: dict[str, Any]) -> list[RegistryIssue]:
    issues: list[RegistryIssue] = []
    allowed_top_level = {
        'schema_version',
        'ignored_secret_names',
        'high_risk_name_patterns',
        'runtime_refresh_methods',
        'secrets',
    }
    for key in sorted(set(registry) - allowed_top_level):
        issues.append(RegistryIssue('ERROR', str(key), 'unknown top-level registry field'))
    for key in sorted(allowed_top_level):
        if key not in registry:
            issues.append(RegistryIssue('ERROR', key, 'missing top-level registry field'))

    ignored = _string_list(registry.get('ignored_secret_names', []))
    secret_entries = registry.get('secrets', {})
    if not isinstance(secret_entries, dict):
        issues.append(RegistryIssue('ERROR', 'secrets', 'secrets must be a mapping'))
        return issues
    for ignored_name in sorted(set(ignored) & set(secret_entries)):
        issues.append(RegistryIssue('ERROR', ignored_name, 'name appears in both secrets and ignored_secret_names'))

    allowed_secret_fields = {'description', 'category', 'owner', 'rotation_verification', 'notes', 'status'}
    required_secret_fields = {'description', 'category', 'owner', 'rotation_verification'}
    for name, entry in sorted(secret_entries.items()):
        if not isinstance(entry, dict):
            issues.append(RegistryIssue('ERROR', str(name), 'secret entry must be a mapping'))
            continue
        missing = sorted(required_secret_fields - set(entry))
        if missing:
            issues.append(RegistryIssue('ERROR', str(name), f'missing required fields: {missing}'))
        unknown = sorted(set(entry) - allowed_secret_fields)
        if unknown:
            issues.append(RegistryIssue('ERROR', str(name), f'unknown secret fields: {unknown}'))
    for pattern in _string_list(registry.get('high_risk_name_patterns', [])):
        try:
            re.compile(pattern)
        except re.error:
            issues.append(RegistryIssue('ERROR', pattern, 'invalid high-risk regex pattern'))
    return issues


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        'Secret Consumer Registry Report',
        f"Status: {report['status']}",
        f"Registry: {report['registry']}",
        f"Registered secrets: {report['registered_secret_count']}",
        f"Deploy/runtime consumers: {report['consumer_count']}",
        '',
    ]
    if report['issues']:
        lines.append('Errors:')
        for issue in report['issues']:
            source = f" ({issue['source']})" if issue.get('source') else ''
            lines.append(f"  - {issue['secret']}: {issue['message']}{source}")
        lines.append('')
    if report['warnings']:
        lines.append('Warnings:')
        for warning in report['warnings']:
            lines.append(f"  - {warning['secret']}: {warning['message']}")
        lines.append('')

    consumers_by_secret: dict[str, list[dict[str, Any]]] = {}
    for consumer in report['consumers']:
        consumers_by_secret.setdefault(consumer['secret'], []).append(consumer)

    lines.append('Consumers:')
    for secret in sorted(consumers_by_secret):
        entries = consumers_by_secret[secret]
        categories = sorted({entry.get('category', 'unregistered') for entry in entries})
        lines.append(f"  - {secret} [{', '.join(categories)}]")
        for entry in entries:
            refresh = entry.get('refresh_after_rotation', '')
            suffix = f"; refresh: {refresh}" if refresh else ''
            lines.append(
                f"      {entry['runtime']}/{entry['environment']}/{entry['service']} "
                f"as {entry['env_name']} from {entry['source']}{suffix}"
            )
    return '\n'.join(lines)


def _consumer_record(
    consumer: Consumer,
    secret_entries: dict[str, Any],
    refresh_methods: dict[str, Any],
) -> dict[str, Any]:
    secret_entry = secret_entries.get(consumer.secret, {})
    if not isinstance(secret_entry, dict):
        secret_entry = {}
    refresh_entry = refresh_methods.get(consumer.runtime, {})
    if not isinstance(refresh_entry, dict):
        refresh_entry = {}
    return {
        **asdict(consumer),
        'category': secret_entry.get('category', 'unregistered'),
        'owner': secret_entry.get('owner', 'unregistered'),
        'rotation_verification': secret_entry.get('rotation_verification', ''),
        'refresh_after_rotation': refresh_entry.get('after_rotation', ''),
        'refresh_verify': refresh_entry.get('verify', ''),
    }


def _consumer_sort_key(consumer: Consumer) -> tuple[str, str, str, str, str]:
    return (consumer.secret, consumer.runtime, consumer.environment, consumer.service, consumer.env_name)


def _dedupe_consumers(consumers: list[Consumer]) -> list[Consumer]:
    seen: set[Consumer] = set()
    result: list[Consumer] = []
    for consumer in consumers:
        if consumer in seen:
            continue
        seen.add(consumer)
        result.append(consumer)
    return result


def _secret_key_from_env_entry(entry: dict[str, Any]) -> str | None:
    value_from = entry.get('valueFrom')
    if not isinstance(value_from, dict):
        return None
    secret_key_ref = value_from.get('secretKeyRef')
    if not isinstance(secret_key_ref, dict):
        return None
    key = secret_key_ref.get('key')
    return key if isinstance(key, str) else None


def _chart_name(charts_dir: Path, path: Path) -> str:
    relative = path.relative_to(charts_dir)
    if len(relative.parts) >= 2 and relative.parts[0] == 'deepgram-self-hosted':
        return '/'.join(relative.parts[:2])
    return relative.parts[0]


def _environment_from_filename(name: str) -> str:
    if name.startswith('prod_'):
        return 'prod'
    if name.startswith('dev_'):
        return 'dev'
    return 'shared'


def _mapping_items(value: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return []
    return [(str(key), entry) for key, entry in value.items() if isinstance(entry, dict)]


def _is_high_risk_name(name: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(name) for pattern in patterns)


def _compile_valid_patterns(value: Any) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for pattern in _string_list(value):
        try:
            patterns.append(re.compile(pattern))
        except re.error:
            continue
    return patterns


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def _load_yaml_or_none(path: Path) -> Any:
    try:
        with path.open('r', encoding='utf-8') as handle:
            return yaml.safe_load(handle)
    except yaml.YAMLError:
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return ''


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == '__main__':
    sys.exit(main())
