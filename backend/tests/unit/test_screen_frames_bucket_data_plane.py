"""Screen-frame bytes follow the customer data plane, not the compute project.

Every dev host serves production Firestore (`data_plane_project: based-hardware`),
so it must write and read the production frame bucket. A dev bucket here puts
production users' screenshots in a dev-readable bucket and hides them from
production notes (the 2026-10-20 finding).
"""

from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]
_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
BUCKET_BY_DATA_PLANE = {'based-hardware': 'based-hardware-prod-screen-frames'}


def _load(text):
    return yaml.load(text, Loader=_LOADER)  # noqa: S506 - safe loader (C implementation when available)


def _values(node, key):
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                yield value
            else:
                yield from _values(value, key)
    elif isinstance(node, list):
        for item in node:
            yield from _values(item, key)


def test_runtime_manifest_screen_frame_bucket_matches_the_data_plane():
    manifest = _load((BACKEND / 'deploy/runtime_env.yaml').read_text())
    for name in ('dev', 'prod'):
        environment = manifest['environments'][name] if 'environments' in manifest else manifest[name]
        overlay = _load((BACKEND / f'deploy/runtime_env/{name}.overlay.yaml').read_text())
        expected = BUCKET_BY_DATA_PLANE[overlay['data_plane_project']]
        found = [binding.get('value') for binding in _values(environment, 'BUCKET_SCREEN_FRAMES')]
        assert found, name
        assert set(found) == {expected}, (name, found)


def test_gke_chart_screen_frame_bucket_matches_the_data_plane():
    for chart in ('backend-listen/dev_omi_backend_listen_values.yaml', 'pusher/dev_omi_pusher_values.yaml'):
        values = _load((BACKEND / 'charts' / chart).read_text())
        env = {item['name']: item.get('value') for item in values['env']}
        assert env['BUCKET_SCREEN_FRAMES'] == BUCKET_BY_DATA_PLANE['based-hardware'], chart
