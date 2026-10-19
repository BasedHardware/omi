"""B8 route census: OMI_ROLE role map vs main.py, task/scheduler targets and websockets."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

import app_roles
from app_roles import AppRole

BACKEND = Path(__file__).resolve().parents[2]
MAIN = BACKEND / 'main.py'


def _main_include_order() -> list[str]:
    """Routers main.py includes directly, in order (empty once main.py mounts through app_roles)."""

    tree = ast.parse(MAIN.read_text(encoding='utf-8'))
    order: list[str] = []

    def visit(nodes):
        for node in nodes:
            if isinstance(node, ast.If):
                visit(node.body)
                visit(node.orelse)
            elif (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and ast.unparse(node.value.func) == 'app.include_router'
            ):
                order.append(ast.unparse(node.value.args[0]))

    visit(tree.body)
    return order


def _main_uses_role_mounts() -> bool:
    return 'mount_routers(' in MAIN.read_text(encoding='utf-8')


def test_all_role_is_exactly_todays_route_table():
    keys = [mount.key for mount in app_roles.ROUTER_MOUNTS]
    assert len(keys) == len(set(keys)), 'a router is mounted twice'
    direct = _main_include_order()
    if _main_uses_role_mounts():
        assert direct == [], 'main.py must mount every router through app_roles, not beside it'
    else:
        assert keys == direct, 'ROUTER_MOUNTS must equal main.py include order (FastAPI matches first route)'


def test_harness_routers_stay_out_of_deployable_route_tables():
    harness = {m.key for m in app_roles.ROUTER_MOUNTS if m.harness_only}
    assert harness == {'chat_first_e2e.router', 'daily_summary_e2e.router'}
    for role in AppRole:
        assert not harness & {m.key for m in app_roles.mounts_for(role)}
    assert harness <= {m.key for m in app_roles.mounts_for(AppRole.ALL, include_harness=True)}


def test_union_of_roles_is_the_all_role():
    union: list[str] = []
    for role in (AppRole.API, AppRole.WORKERS, AppRole.REALTIME):
        union.extend(m.key for m in app_roles.mounts_for(role))
    assert set(union) == {m.key for m in app_roles.mounts_for(AppRole.ALL)}
    for mount in app_roles.ROUTER_MOUNTS:
        assert mount.roles and AppRole.ALL not in mount.roles


def _module_for_path(path: str) -> set[str]:
    owners = set()
    for file in (BACKEND / 'routers').glob('*.py'):
        text = file.read_text(encoding='utf-8')
        if path in text:
            owners.add(file.stem)
            continue
        for prefix in re.findall(r"APIRouter\([^)]*prefix=['\"]([^'\"]+)['\"]", text):
            rest = path[len(prefix) :]
            if path.startswith(prefix) and rest and (f"'{rest}'" in text or f'"{rest}"' in text):
                owners.add(file.stem)
    return owners


def _task_edge_routes() -> set[str]:
    text = (BACKEND / 'scripts/cross_service_contract.py').read_text(encoding='utf-8')
    return set(re.findall(r"route='(/v\d[^']*)'", text))


def _scheduler_backend_paths() -> set[str]:
    jobs = yaml.safe_load((BACKEND / 'deploy/scheduler/jobs.yaml').read_text(encoding='utf-8'))
    paths = set()
    for env in jobs['environments'].values():
        for job in env['jobs']:
            uri = str((job.get('target') or {}).get('uri') or '')
            match = re.match(r'https://backend(?:-[a-z]+)*-[a-z0-9]+-uc\.a\.run\.app(/v\d[^?]*)', uri)
            if match:
                paths.add(match.group(1))
    return paths


@pytest.mark.parametrize('path', sorted(_task_edge_routes() | {'/v2/sync-backfill-sequencer/sweep'}))
def test_every_task_and_scheduler_target_is_served_by_workers(path):
    owners = _module_for_path(path)
    assert owners, f'no router defines {path}'
    workers = {m.module for m in app_roles.mounts_for(AppRole.WORKERS)}
    assert owners & workers, f'{path} (in {sorted(owners)}) is not mounted by the workers role'


def test_scheduler_targets_on_backend_services_are_served_by_workers():
    paths = _scheduler_backend_paths()
    assert '/v2/dream-agent/sweep' in paths and '/v2/candidate-integrations/sweep' in paths
    workers = {m.module for m in app_roles.mounts_for(AppRole.WORKERS)}
    for path in paths:
        assert _module_for_path(path) & workers, path


def test_every_websocket_router_is_mounted_by_realtime():
    realtime = {m.module for m in app_roles.mounts_for(AppRole.REALTIME)}
    mounted = {m.module for m in app_roles.ROUTER_MOUNTS}
    for file in (BACKEND / 'routers').glob('*.py'):
        if file.stem in mounted and re.search(r'@router\.websocket\(', file.read_text(encoding='utf-8')):
            assert file.stem in realtime, file.stem


@pytest.mark.parametrize(
    'raw, role',
    [
        (None, AppRole.ALL),
        ('', AppRole.ALL),
        ('all', AppRole.ALL),
        (' Workers ', AppRole.WORKERS),
        ('api', AppRole.API),
    ],
)
def test_role_from_env(raw, role):
    environ = {} if raw is None else {'OMI_ROLE': raw}
    assert app_roles.role_from_env(environ) is role


def test_unknown_role_fails_startup():
    with pytest.raises(app_roles.RoleConfigError, match='OMI_ROLE'):
        app_roles.role_from_env({'OMI_ROLE': 'worker'})


def test_mount_routers_includes_in_order_from_the_namespace():
    class FakeApp:
        def __init__(self):
            self.routers = []

        def include_router(self, router):
            self.routers.append(router)

    class Module:
        def __init__(self, name):
            self.router = f'{name}.router'
            self.mcp_router = f'{name}.mcp_router'
            self.developer_router = f'{name}.developer_router'

    namespace = {m.module: Module(m.module) for m in app_roles.ROUTER_MOUNTS}
    app = FakeApp()
    count = app_roles.mount_routers(app, AppRole.WORKERS, namespace)
    assert count == len(app.routers)
    assert app.routers == [f'{m.module}.{m.attr}' for m in app_roles.mounts_for(AppRole.WORKERS)]
    assert 'sync.router' in app.routers and 'transcribe.router' not in app.routers
