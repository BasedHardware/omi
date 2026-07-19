from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'verify-llm-gateway-serving.py'
SPEC = importlib.util.spec_from_file_location('verify_llm_gateway_serving', SCRIPT)
assert SPEC is not None and SPEC.loader is not None


@pytest.fixture
def gateway_gate(monkeypatch):
    module = importlib.util.module_from_spec(SPEC)
    monkeypatch.setitem(sys.modules, SPEC.name, module)
    SPEC.loader.exec_module(module)
    return module


def _runner(responses: dict[str, object], calls: list[list[str]]):
    def run(command: list[str]) -> str:
        calls.append(command)
        if command[:5] == ['gcloud', 'compute', 'forwarding-rules', 'list', '--project']:
            key = 'gcloud compute forwarding-rules list'
        elif command[:4] == ['gcloud', 'compute', 'addresses', 'describe']:
            key = f'gcloud compute addresses describe {command[4]}'
        else:
            key = ' '.join(command[:6])
        return json.dumps(responses[key])

    return run


def _healthy_responses() -> dict[str, object]:
    return {
        'kubectl -n prod-omi-backend get deployment prod-omi-llm-gateway': {
            'status': {
                'availableReplicas': 1,
                'readyReplicas': 1,
                'conditions': [{'type': 'Available', 'status': 'True'}],
            }
        },
        'kubectl -n prod-omi-backend get service prod-omi-llm-gateway': {'metadata': {'name': 'prod-omi-llm-gateway'}},
        'kubectl -n prod-omi-backend get endpointslice -l': {
            'items': [{'endpoints': [{'conditions': {'ready': True}, 'addresses': ['10.0.0.8']}]}]
        },
        'kubectl -n prod-omi-backend get ingress prod-omi-llm-gateway': {
            'metadata': {
                'annotations': {'kubernetes.io/ingress.regional-static-ip-name': 'prod-omi-self-hosted-llm-ip-address'}
            },
            'status': {'loadBalancer': {'ingress': [{'ip': '172.16.160.108'}]}},
        },
        'gcloud compute addresses describe prod-omi-self-hosted-llm-ip-address': {'address': '172.16.160.108'},
        'gcloud compute forwarding-rules list': [
            {'IPAddress': '172.16.160.108', 'loadBalancingScheme': 'INTERNAL_MANAGED'}
        ],
    }


def test_gateway_promotion_intent_tracks_runtime_and_helm_listener_surfaces(gateway_gate, tmp_path: Path) -> None:
    manifest = Path(__file__).resolve().parents[2] / 'deploy' / 'runtime_env.yaml'

    assert gateway_gate.gateway_promotion_requested(manifest_path=manifest, environment='prod') is False

    listener_values = tmp_path / 'prod_listener_values.yaml'
    listener_values.write_text('env:\n  - name: OMI_LLM_GATEWAY_FEATURE_MODE\n    value: gateway\n', encoding='utf-8')
    assert (
        gateway_gate.gateway_promotion_requested(
            manifest_path=manifest,
            environment='prod',
            listener_values_path=listener_values,
        )
        is True
    )


def test_verify_gateway_serving_derives_url_only_from_ready_attached_ilb(gateway_gate) -> None:
    calls: list[list[str]] = []
    target = gateway_gate.GatewayTarget(
        namespace='prod-omi-backend',
        release_name='prod-omi-llm-gateway',
        ingress_name='prod-omi-llm-gateway',
        static_address_name='prod-omi-self-hosted-llm-ip-address',
    )

    url = gateway_gate.verify_gateway_serving(
        target=target,
        project='based-hardware',
        region='us-central1',
        run=_runner(_healthy_responses(), calls),
    )

    assert url == 'http://172.16.160.108'
    assert any(command[0:4] == ['kubectl', '-n', 'prod-omi-backend', 'get'] for command in calls)
    assert any(command[0:3] == ['gcloud', 'compute', 'forwarding-rules'] for command in calls)


def test_verify_gateway_serving_rejects_reserved_address_without_forwarding_rule(gateway_gate) -> None:
    responses = _healthy_responses()
    responses['gcloud compute forwarding-rules list'] = []
    target = gateway_gate.GatewayTarget(
        namespace='prod-omi-backend',
        release_name='prod-omi-llm-gateway',
        ingress_name='prod-omi-llm-gateway',
        static_address_name='prod-omi-self-hosted-llm-ip-address',
    )

    with pytest.raises(RuntimeError, match='no internal forwarding rule'):
        gateway_gate.verify_gateway_serving(
            target=target,
            project='based-hardware',
            region='us-central1',
            run=_runner(responses, []),
        )
