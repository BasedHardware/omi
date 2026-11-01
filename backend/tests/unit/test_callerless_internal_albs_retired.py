"""Prod diarizer and nllb-translation must not pay for callerless internal ALBs.

Both services moved their callers to the shared internal gateway
(prod-omi-internal-gateway, 172.16.160.20) and ClusterIP DNS. Their per-service
gce-internal ingresses had no callers left and billed a proxy instance each
(~$1.61/day per rule). This pins the retirement: the prod ingresses stay
disabled while the shared-gateway routes stay enabled, so a silent re-enable
or an accidental route removal fails here first. Rollback is a values flip;
the ALB re-forms on the reserved static IP.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]

RETIRED_INGRESSES = {
    'diarizer': 'prod-diarizer-ilb-ip-address',
    'nllb-translation': 'prod-nllb-translation-ilb-ip-address',
}
GATEWAY_NAME = 'prod-omi-internal-gateway'


def _prod_values(chart: str) -> dict:
    path = ROOT / f'backend/charts/{chart}/prod_omi_{chart.replace("-", "_")}_values.yaml'
    return yaml.load(path.read_text(), Loader=yaml.CSafeLoader)


def test_retired_prod_ingresses_stay_disabled() -> None:
    for chart, static_ip in RETIRED_INGRESSES.items():
        values = _prod_values(chart)
        assert values['ingress']['enabled'] is False, chart
        # The rollback path must stay declarative: same reserved address.
        assert values['ingress']['annotations']['kubernetes.io/ingress.regional-static-ip-name'] == static_ip, chart


def test_shared_gateway_routes_stay_enabled_for_cloud_run_callers() -> None:
    for chart in RETIRED_INGRESSES:
        gateway = _prod_values(chart)['gateway']
        assert gateway['enabled'] is True, chart
        assert gateway['name'] == GATEWAY_NAME, chart
