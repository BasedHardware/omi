"""Dream lanes derive reservation policy from the gateway's own desktop lanes.

Before #20960, both stages are Luna. With its reserved-only artifact installed,
reasoning reuses dedicated capacity + Luna fallback, never a shared Vertex route.
"""

from copy import deepcopy


def dream_lane_items(desktop_lanes, desktop_artifacts):
    lanes, artifacts = [], []
    for stage in ('triage', 'reasoning'):
        lane = deepcopy(desktop_lanes[0])
        route = deepcopy(desktop_artifacts[0])
        reserved = (
            stage == 'reasoning'
            and route['provider_options'].get('reserved_capacity_only') is True
            and route['fallbacks'] == [{'provider': 'openai', 'model': 'gpt-6-luna'}]
            and 'reserved_capacity_unavailable' in route['fallback_policy']['fallback_on']
        )
        lane_id = 'omi:auto:dream-' + stage
        route_id = 'route.dream_' + stage + '.001'
        capabilities = {
            'text_input': True,
            'streaming': False,
            'structured_output': 'json_schema',
            'tools': False,
            'translation': False,
        }
        lane.update(lane_id=lane_id, active_route=route_id, last_known_good=route_id, capabilities=capabilities)
        route.update(
            lane_id=lane_id,
            route_artifact_id=route_id,
            capabilities=capabilities,
            timeouts={'request_ms': 60000},
            retry={'max_attempts': 1},
        )
        route['evidence'] = {
            'benchmark_snapshot': 'dream.shadow.v1',
            'eval_report': 'backend.tests.unit.test_dream_agent',
            'benchmark_source': 'omi_eval',
            'dev_only': False,
        }
        if not reserved:
            route.update(
                primary={'provider': 'openai', 'model': 'gpt-6-luna'},
                fallbacks=[],
                provider_options={'reasoning_effort': 'none'},
            )
            route['fallback_policy']['fallback_on'] = []
            route['credential_policy']['fallback_eligible_failure_classes'] = []
            lane['credential_policy'] = deepcopy(route['credential_policy'])
        lanes.append(lane)
        artifacts.append(route)
    return lanes, artifacts
