"""Hermetic production-handler tests for ambiguous project/parent-task resolution."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class App:
    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def mount(self, *args, **kwargs):
        pass


class Response:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error


def load_app():
    modules = {}
    definitions = {
        'fastapi': dict(FastAPI=App, HTTPException=Exception, Request=SimpleNamespace, Query=Mock(), Form=Mock()),
        'fastapi.responses': dict(HTMLResponse=Mock(), RedirectResponse=Mock(), JSONResponse=Mock()),
        'fastapi.staticfiles': dict(StaticFiles=Mock()),
        'fastapi.templating': dict(Jinja2Templates=Mock()),
        'dotenv': dict(load_dotenv=lambda: None),
        'requests': dict(
            post=Mock(side_effect=AssertionError('Unexpected HTTP')),
            get=Mock(side_effect=AssertionError('Unexpected HTTP')),
            request=Mock(side_effect=AssertionError('Unexpected HTTP')),
            RequestException=Exception),
        'db': {name: Mock(side_effect=AssertionError('Unexpected storage')) for name in (
            'store_hive_credentials', 'get_hive_credentials', 'delete_hive_credentials',
            'is_connected', 'store_default_project', 'get_default_project', 'get_user_settings')},
        'models': dict(ChatToolResponse=Response, HiveProject=SimpleNamespace,
                       HiveTask=SimpleNamespace, HiveAction=SimpleNamespace),
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('hive_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


def project(pid, name):
    return SimpleNamespace(id=pid, name=name, description=None, status=None, workspace_id='ws-1')


def task(tid, name, project_id, project_name='Marketing'):
    return SimpleNamespace(id=tid, name=name, description=None, status=None,
                           project_id=project_id, project_name=project_name, assignees=[])


class CreateTaskResolutionTests(unittest.TestCase):
    def run_create(self, module, project_name='Q3', parent_task_name=None,
                   search_results=None, rest_result=None):
        module.is_connected = lambda uid: True
        module.get_user_projects = lambda uid, workspace_id=None: [
            project('marketing-id', 'Q3 Marketing'),
            project('sales-id', 'Q3 Sales'),
        ]
        module.get_hive_credentials = lambda uid: {'workspace_id': 'ws-1'}
        if search_results is None:
            search_results = [task('other-project-task', 'Website refresh', 'some-other-project', 'Website')]
        module.search_tasks = Mock(return_value=search_results)
        module.hive_rest_request = Mock(return_value=rest_result or {'errors': [{'message': 'no create should happen'}]})

        payload = dict(uid='fixture-user', task_name='New task', project_name=project_name,
                       parent_task_name=parent_task_name)

        async def json():
            return payload

        return asyncio.run(module.tool_hive_create_task(SimpleNamespace(json=json)))

    def test_ambiguous_project_name_refuses_to_create(self):
        module = load_app()
        response = self.run_create(module, project_name='Q3')
        self.assertIsNone(response.result)
        self.assertIn('Q3 Marketing', response.error)
        self.assertIn('Q3 Sales', response.error)

    def test_unique_project_name_still_resolves(self):
        module = load_app()
        response = self.run_create(module, project_name='Q3 Sales',
                                   search_results=[], rest_result={'id': 'new-task'})
        self.assertIsNone(response.error)
        self.assertIn('Q3 Sales', response.result)

    def test_parent_outside_target_project_is_never_used(self):
        module = load_app()
        response = self.run_create(module, project_name='Q3 Sales', parent_task_name='Website refresh')
        self.assertIsNone(response.result)
        self.assertIn('No task named', response.error)
        module.hive_rest_request.assert_not_called()

    def test_ambiguous_parent_inside_target_project_refuses(self):
        module = load_app()
        response = self.run_create(module, project_name='Q3 Sales', parent_task_name='Website refresh',
                                   search_results=[
                                       task('staging-1', 'Website refresh', 'sales-id'),
                                       task('staging-2', 'Website refresh', 'sales-id'),
                                   ])
        self.assertIsNone(response.result)
        self.assertIn('Multiple tasks', response.error)
        module.hive_rest_request.assert_not_called()

    def test_unique_parent_inside_target_project_is_used(self):
        module = load_app()
        module.hive_rest_request = Mock(return_value={'id': 'new-task'})
        response = self.run_create(module, project_name='Q3 Sales', parent_task_name='Website refresh',
                                   search_results=[task('the-parent', 'Website refresh', 'sales-id')],
                                   rest_result={'id': 'new-task'})
        self.assertIsNone(response.error)
        self.assertIn('sub-task', response.result)

    def test_parent_task_id_bypasses_lookup(self):
        module = load_app()
        module.search_tasks = Mock(side_effect=AssertionError('Unexpected search'))
        module.hive_rest_request = Mock(return_value={'id': 'new-task'})
        module.get_user_projects = lambda uid, workspace_id=None: [project('sales-id', 'Q3 Sales')]
        module.is_connected = lambda uid: True
        module.get_hive_credentials = lambda uid: {'workspace_id': 'ws-1'}
        payload = dict(uid='fixture-user', task_name='New task', project_name='Q3 Sales',
                       parent_task_id='parent-1')

        async def json():
            return payload

        response = asyncio.run(module.tool_hive_create_task(SimpleNamespace(json=json)))
        self.assertIsNone(response.error)
        module.hive_rest_request.assert_called_once()

    def test_find_project_by_name_returns_candidates(self):
        module = load_app()
        module.get_user_projects = lambda uid, workspace_id=None: [
            project('a', 'Q3 Marketing'), project('b', 'Q3 Sales'), project('c', 'Website'),
        ]
        resolved, candidates = module.find_project_by_name('uid', 'Q3 Sales')
        self.assertEqual(resolved.id, 'b')
        self.assertEqual([c.id for c in candidates], ['b'])
        resolved, candidates = module.find_project_by_name('uid', 'Q3')
        self.assertIsNone(resolved)
        self.assertEqual([c.id for c in candidates], ['a', 'b'])
        resolved, candidates = module.find_project_by_name('uid', 'Nope')
        self.assertIsNone(resolved)
        self.assertEqual(candidates, [])


if __name__ == '__main__':
    unittest.main()
