#!/usr/bin/env python3
"""Fail closed before a backend deploy can enable the LLM gateway route.

This intentionally checks the serving data plane rather than treating a
reserved address as evidence of a reachable gateway.  The emitted URL is
derived from the ILB address only after Kubernetes and Compute agree on its
attachment, so Cloud Run never receives a hand-maintained static IP.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
BACKEND_LISTEN_VALUES_DIR = ROOT / 'backend/charts/backend-listen'

CommandRunner = Callable[[list[str]], str]
JsonDict = dict[str, Any]


@dataclass(frozen=True)
class GatewayTarget:
    namespace: str
    release_name: str
    ingress_name: str
    static_address_name: str


def _as_dict(value: object) -> JsonDict:
    if not isinstance(value, dict):
        raise ValueError('expected a mapping')
    return cast(JsonDict, value)


def load_gateway_target(*, manifest_path: Path, environment: str) -> GatewayTarget:
    with manifest_path.open('r', encoding='utf-8') as handle:
        manifest = _as_dict(yaml.safe_load(handle))
    environments = _as_dict(manifest.get('environments'))
    environment_config = _as_dict(environments.get(environment))
    gateway = _as_dict(environment_config.get('llm_gateway'))
    fields = ('namespace', 'release_name', 'ingress_name', 'static_address_name')
    missing = [field for field in fields if not isinstance(gateway.get(field), str) or not gateway[field].strip()]
    if missing:
        raise ValueError(f'{environment}.llm_gateway missing {", ".join(missing)}')
    return GatewayTarget(**{field: str(gateway[field]) for field in fields})


def gateway_promotion_requested(
    *, manifest_path: Path, environment: str, listener_values_path: Path | None = None
) -> bool:
    """Return whether any backend surface requests gateway-first serving."""

    with manifest_path.open('r', encoding='utf-8') as handle:
        manifest = _as_dict(yaml.safe_load(handle))
    environment_config = _as_dict(_as_dict(manifest.get('environments')).get(environment))
    for env_entries in _gateway_mode_env_maps(environment_config):
        if _gateway_mode_enabled(env_entries.get('OMI_LLM_GATEWAY_FEATURE_MODE')):
            return True
    values_path = listener_values_path or BACKEND_LISTEN_VALUES_DIR / f'{environment}_omi_backend_listen_values.yaml'
    with values_path.open('r', encoding='utf-8') as handle:
        listener_values = _as_dict(yaml.safe_load(handle))
    listener_env = listener_values.get('env')
    if not isinstance(listener_env, list):
        raise ValueError(f'{values_path} missing env list')
    return any(
        isinstance(entry, Mapping)
        and entry.get('name') == 'OMI_LLM_GATEWAY_FEATURE_MODE'
        and _gateway_mode_enabled(entry.get('value'))
        for entry in listener_env
    )


def _gateway_mode_enabled(mode: object) -> bool:
    if isinstance(mode, Mapping):
        mode = mode.get('value', '')
    return str(mode).strip().lower() in {'1', 'true', 'yes', 'gateway'}


def _gateway_mode_env_maps(environment_config: JsonDict) -> list[Mapping[str, object]]:
    env_maps: list[Mapping[str, object]] = []
    gke = environment_config.get('gke')
    if isinstance(gke, Mapping):
        for component in gke.values():
            if isinstance(component, Mapping) and isinstance(component.get('env'), Mapping):
                env_maps.append(cast(Mapping[str, object], component['env']))
    cloud_run = environment_config.get('cloud_run')
    if isinstance(cloud_run, Mapping) and isinstance(cloud_run.get('services'), Mapping):
        for service in cloud_run['services'].values():
            if isinstance(service, Mapping) and isinstance(service.get('env'), Mapping):
                env_maps.append(cast(Mapping[str, object], service['env']))
    return env_maps


def verify_gateway_serving(
    *,
    target: GatewayTarget,
    project: str,
    region: str,
    run: CommandRunner,
) -> str:
    """Verify ready workload, endpoints, ingress, and attached internal ILB."""

    deployment = _json(run, ['kubectl', '-n', target.namespace, 'get', 'deployment', target.release_name, '-o', 'json'])
    if not _deployment_available(deployment):
        raise RuntimeError(f'deployment/{target.release_name} is not Available with ready replicas')

    _json(run, ['kubectl', '-n', target.namespace, 'get', 'service', target.release_name, '-o', 'json'])
    endpoint_slices = _json(
        run,
        [
            'kubectl',
            '-n',
            target.namespace,
            'get',
            'endpointslice',
            '-l',
            f'kubernetes.io/service-name={target.release_name}',
            '-o',
            'json',
        ],
    )
    if not _has_ready_endpoint(endpoint_slices):
        raise RuntimeError(f'service/{target.release_name} has no Ready EndpointSlice endpoint')

    ingress = _json(run, ['kubectl', '-n', target.namespace, 'get', 'ingress', target.ingress_name, '-o', 'json'])
    annotations = _mapping_at(ingress, 'metadata', 'annotations')
    declared_address = annotations.get('kubernetes.io/ingress.regional-static-ip-name')
    if declared_address != target.static_address_name:
        raise RuntimeError(
            f'ingress/{target.ingress_name} must declare regional static address {target.static_address_name!r}'
        )

    address = _json(
        run,
        [
            'gcloud',
            'compute',
            'addresses',
            'describe',
            target.static_address_name,
            '--project',
            project,
            '--region',
            region,
            '--format=json',
        ],
    )
    address_ip = str(address.get('address', '')).strip()
    if not address_ip:
        raise RuntimeError(f'address/{target.static_address_name} has no assigned IP')
    if address_ip not in _ingress_ips(ingress):
        raise RuntimeError(f'ingress/{target.ingress_name} is not attached to address {address_ip}')

    forwarding_rules = _json(
        run,
        [
            'gcloud',
            'compute',
            'forwarding-rules',
            'list',
            '--project',
            project,
            '--regions',
            region,
            '--format=json',
        ],
    )
    if not _has_attached_internal_forwarding_rule(forwarding_rules, address_ip):
        raise RuntimeError(f'no internal forwarding rule in {region} is attached to {address_ip}')
    return f'http://{address_ip}'


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout


def _json(run: CommandRunner, command: list[str]) -> JsonDict:
    try:
        loaded = json.loads(run(command))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'command did not return JSON: {" ".join(command[:4])}') from exc
    if isinstance(loaded, list):
        return {'items': loaded}
    return _as_dict(loaded)


def _deployment_available(deployment: JsonDict) -> bool:
    status = _mapping_at(deployment, 'status')
    if int(status.get('availableReplicas', 0) or 0) < 1 or int(status.get('readyReplicas', 0) or 0) < 1:
        return False
    conditions = status.get('conditions')
    return isinstance(conditions, list) and any(
        isinstance(condition, Mapping)
        and condition.get('type') == 'Available'
        and str(condition.get('status')).lower() == 'true'
        for condition in conditions
    )


def _has_ready_endpoint(endpoint_slices: JsonDict) -> bool:
    items = endpoint_slices.get('items')
    if not isinstance(items, list):
        return False
    for endpoint_slice in items:
        if not isinstance(endpoint_slice, Mapping):
            continue
        endpoints = endpoint_slice.get('endpoints')
        if not isinstance(endpoints, list):
            continue
        for endpoint in endpoints:
            if not isinstance(endpoint, Mapping):
                continue
            conditions = endpoint.get('conditions')
            ready = conditions.get('ready') if isinstance(conditions, Mapping) else None
            addresses = endpoint.get('addresses')
            if (
                ready is True
                and isinstance(addresses, list)
                and any(isinstance(address, str) and address for address in addresses)
            ):
                return True
    return False


def _ingress_ips(ingress: JsonDict) -> set[str]:
    load_balancer = _mapping_at(ingress, 'status', 'loadBalancer')
    entries = load_balancer.get('ingress')
    if not isinstance(entries, list):
        return set()
    return {
        str(entry['ip']).strip()
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get('ip'), str) and entry['ip'].strip()
    }


def _has_attached_internal_forwarding_rule(forwarding_rules: JsonDict, address_ip: str) -> bool:
    items = forwarding_rules.get('items')
    if not isinstance(items, list):
        return False
    return any(
        isinstance(rule, Mapping)
        and str(rule.get('IPAddress', '')).strip() == address_ip
        and str(rule.get('loadBalancingScheme', '')).upper().startswith('INTERNAL')
        for rule in items
    )


def _mapping_at(value: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    current: object = value
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return cast(Mapping[str, Any], current) if isinstance(current, Mapping) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('dev', 'prod'), required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--listener-values',
        type=Path,
        help='The exact backend-listen Helm values file this deploy will apply.',
    )
    parser.add_argument(
        '--intent-only', action='store_true', help='Print whether this manifest requests gateway-first serving.'
    )
    parser.add_argument('--github-output', type=Path, help='Write gateway_url to this GitHub Actions output file.')
    args = parser.parse_args()

    if args.intent_only:
        print(
            'enabled='
            f'{str(gateway_promotion_requested(manifest_path=args.manifest, environment=args.environment, listener_values_path=args.listener_values)).lower()}'
        )
        return 0

    target = load_gateway_target(manifest_path=args.manifest, environment=args.environment)
    gateway_url = verify_gateway_serving(target=target, project=args.project, region=args.region, run=_run)
    print(f'LLM gateway serving gate passed: {gateway_url}')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as handle:
            handle.write(f'gateway_url={gateway_url}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
