"""Cloud Logging views preserve log evidence without pretending to provide LogQL rates."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = ROOT / 'backend/charts/monitoring/dashboards/omi-services/omi-services-overview.json'


def test_overview_log_panels_use_supported_cloud_logging_models():
    dashboard = json.loads(DASHBOARD.read_text())
    assert 'aet29e27cgmwwc' not in DASHBOARD.read_text()
    panels = {p['id']: p for p in dashboard['panels'] if p['id'] in {59, 60, 62, 63}}
    assert len(panels) == 4
    assert sum(len(p['targets']) for p in panels.values()) == 7
    for panel in panels.values():
        assert panel['type'] == 'logs'
        assert 'logs (Cloud Logging)' in panel['title']
        assert 'not requests per second or numeric error rates' in panel['description']
        assert panel['fieldConfig']['overrides'] == []
        for target in panel['targets']:
            assert (
                target['datasource']
                == panel['datasource']
                == {
                    'type': 'googlecloud-logging-datasource',
                    'uid': 'deuxlwt1d569sb',
                }
            )
            assert target['projectId'] == 'based-hardware'
            query = target['queryText']
            for scope in [
                'resource.type="k8s_container"',
                'resource.labels.project_id="based-hardware"',
                'resource.labels.cluster_name="prod-omi-gke"',
                'resource.labels.namespace_name="prod-omi-backend"',
                'resource.labels.container_name="backend-listen"',
            ]:
                assert scope in query
            assert 'textPayload=~' in query and 'jsonPayload.message=~' in query
            assert '$' not in query  # no unverified template interpolation
            assert 'expr' not in target
    assert 'NOT (textPayload=~"_listen.*end"' in panels[59]['targets'][1]['queryText']
    assert panels[59]['targets'][0]['hide'] is True
