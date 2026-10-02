"""Hermetic regression tests for plugins/omi-github-app/main.py create_issue.

Standard library only: fastapi, dotenv, simple_storage, github_client,
issue_detector, models, and agent_providers are replaced with minimal stubs
before loading the module under test so the suite runs under plain python3.

create_issue advertises `auto_labels` as "If true (default), use AI to
automatically select appropriate labels". It read that flag with
`body.get("auto_labels", True)`, but dict.get returns None -- not the
default -- when the key is present and null, which is what the backend sends
for an omitted optional parameter. None is falsy, so `if auto_labels and not
labels:` never ran and AI label selection was silently disabled on exactly
the path the schema documents as default-on. No error surfaced; issues were
just created unlabelled. An omitted or null flag must resolve to True, while
an explicit false must still opt out.
"""
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


class StubGitHubClient:
    """Records label traffic so tests can assert on auto-selection."""

    def __init__(self):
        self.repo_labels = ['bug', 'enhancement']
        self.created = []

    def get_repo_labels(self, access_token, repo_full_name):
        return list(self.repo_labels)

    async def create_issue(self, access_token, repo_full_name, title, body, labels):
        self.created.append(dict(repo=repo_full_name, title=title, labels=labels))
        return dict(success=True, issue_url='https://github.com/o/r/issues/1', issue_number=1)


def load_app(selected_labels=('bug',)):
    modules = {}
    selected = list(selected_labels)

    async def ai_select_labels(title, body, repo_labels):
        ai_select_labels.calls.append((title, body, list(repo_labels)))
        return list(selected)

    ai_select_labels.calls = []

    definitions = {
        'fastapi': dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock()),
        'fastapi.responses': dict(HTMLResponse=object, RedirectResponse=Mock()),
        'dotenv': dict(load_dotenv=lambda: None),
        'simple_storage': dict(SimpleUserStorage=SimpleNamespace(
            get_user=lambda uid: {'access_token': 'token', 'default_repo': 'owner/repo'})),
        'github_client': dict(GitHubClient=StubGitHubClient),
        'issue_detector': dict(ai_select_labels=ai_select_labels),
        'models': dict(ChatToolResponse=Response),
        'agent_providers': dict(
            run_agent_provider=Mock(), PROVIDERS={}, get_provider_label=Mock(),
            get_provider_default_key=Mock(), get_provider_base_url=Mock()),
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('github_app_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    module._ai_select_labels = ai_select_labels
    return module


class CreateIssueAutoLabelsTests(unittest.TestCase):
    def run_create(self, payload, selected_labels=('bug',)):
        module = load_app(selected_labels)
        module.get_repo_for_request = lambda user, repo_param=None: ('owner/repo', None)
        body = dict(uid='fixture-user', title='Fixture issue')
        body.update(payload)

        async def json():
            return body

        response = asyncio.run(module.tool_create_issue(SimpleNamespace(json=json)))
        return response, module

    def test_omitted_or_null_flag_keeps_the_documented_default(self):
        # The schema says auto_labels defaults to true; an absent key and the
        # explicit null the backend sends for it must behave identically.
        for label, payload in (('absent', {}), ('null', {'auto_labels': None})):
            with self.subTest(flag=label):
                response, module = self.run_create(payload)
                self.assertIsNone(response.error)
                self.assertEqual(len(module._ai_select_labels.calls), 1,
                                 'AI label selection must run when the flag is omitted')
                self.assertEqual(module.github_client.created[-1]['labels'], ['bug'])

    def test_explicit_false_still_opts_out(self):
        response, module = self.run_create({'auto_labels': False})
        self.assertIsNone(response.error)
        self.assertEqual(module._ai_select_labels.calls, [])
        self.assertEqual(module.github_client.created[-1]['labels'], [])

    def test_explicit_true_runs_selection(self):
        response, module = self.run_create({'auto_labels': True})
        self.assertIsNone(response.error)
        self.assertEqual(len(module._ai_select_labels.calls), 1)

    def test_caller_supplied_labels_short_circuit_auto_selection(self):
        # Explicit labels win regardless of the flag; auto-selection only
        # fills the gap when the caller supplied none.
        response, module = self.run_create({'labels': ['enhancement']})
        self.assertIsNone(response.error)
        self.assertEqual(module._ai_select_labels.calls, [])
        self.assertEqual(module.github_client.created[-1]['labels'], ['enhancement'])

    def test_blank_and_null_labels_fall_back_to_auto_selection(self):
        # A null/empty labels payload is not a caller choice, so the
        # documented default should still apply.
        for label, payload in (
            ('null-labels', {'labels': None}),
            ('empty-list', {'labels': []}),
            ('blank-string', {'labels': '  '}),
            ('list-of-nulls', {'labels': [None, '  ']}),
        ):
            with self.subTest(labels=label):
                response, module = self.run_create(payload)
                self.assertIsNone(response.error)
                self.assertEqual(len(module._ai_select_labels.calls), 1)


if __name__ == '__main__':
    unittest.main()
