"""Hermetic production-handler tests for team disambiguation, issue
identifier sanitization, and null-field safety (issue #14344).

Covers the failure modes the issue reports:
  - tool_create_issue silently creating issues in teams[0] when the user
    belongs to several teams, and failing GraphQL when given a team key
    or name instead of a UUID
  - dirty issue identifiers ("#ENG-123", "issue: #ENG-123", full web
    URLs, untyped values) reaching the exact-issue lookup
  - null optional fields (team/state/project/labels, nodes: null)
    crashing tool_get_issue / tool_update_issue_status with
    AttributeError/KeyError/TypeError
  - whitespace-only or untyped status values leaking into
    find_state_by_name partial matching
  - the omi-tools manifest omitting the team and status parameters

Run: python3 plugins/omi-linear-app/test_team_disambiguation.py
"""
import asyncio
import importlib.util
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent


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
        'fastapi': dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock()),
        'fastapi.responses': dict(HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        'fastapi.staticfiles': dict(StaticFiles=Mock()),
        'fastapi.templating': dict(Jinja2Templates=Mock()),
        'dotenv': dict(load_dotenv=lambda: None),
        'requests': dict(post=Mock(side_effect=AssertionError('Unexpected HTTP')), RequestException=Exception),
        'db': {name: Mock(side_effect=AssertionError('Unexpected storage')) for name in (
            'store_linear_tokens', 'get_linear_tokens', 'delete_linear_tokens', 'is_token_expired',
            'store_default_team', 'get_default_team', 'get_user_settings')},
        'models': {name: Response if name == 'ChatToolResponse' else SimpleNamespace for name in (
            'ChatToolResponse', 'LinearIssue', 'LinearTeam', 'LinearProject', 'LinearComment', 'LinearUser', 'WorkflowState')},
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('linear_under_test_disambiguation', ROOT / 'main.py')
    module = importlib.util.module_from_spec(spec)
    import os
    with __import__('unittest').mock.patch.dict(sys.modules, modules), \
            __import__('unittest').mock.patch.dict(os.environ, {}, clear=True):
        spec.loader.exec_module(module)
    return module


def team(id, name, key):
    return SimpleNamespace(id=id, name=name, key=key)


TEAMS = [
    team('uuid-eng', 'Engineering', 'ENG'),
    team('uuid-design', 'Design', 'DES'),
    team('uuid-marketing', 'Marketing', 'MKT'),
]

ISSUE = dict(id='exact-id', identifier='ENG-123', title='Exact issue', url='https://linear.app/example',
             team=dict(id='team-id', name='Engineering'), state=dict(name='Todo'), labels=dict(nodes=[]))


def drive(module, handler, body):
    payload = dict(uid='fixture-user', **body)

    async def json():
        return payload

    return asyncio.run(getattr(module, handler)(SimpleNamespace(json=json)))


def patch_common(module, teams=TEAMS, default=None, lookup=None):
    module.get_linear_tokens = lambda uid: True
    module.get_default_team = lambda uid: default
    module.get_user_teams = lambda uid: list(teams)
    module.linear_graphql_request = Mock(return_value={'issue': ISSUE})


class ResolveTeamTests(unittest.TestCase):
    def test_uuid_exact_match(self):
        module = load_app()
        patch_common(module)
        resolved = module.resolve_team('fixture-user', 'uuid-design')
        self.assertEqual(resolved['team'].id, 'uuid-design')

    def test_key_match_is_case_insensitive(self):
        module = load_app()
        patch_common(module)
        self.assertEqual(module.resolve_team('fixture-user', 'eng')['team'].id, 'uuid-eng')
        self.assertEqual(module.resolve_team('fixture-user', 'ENG')['team'].id, 'uuid-eng')

    def test_name_match(self):
        module = load_app()
        patch_common(module)
        self.assertEqual(module.resolve_team('fixture-user', 'Marketing')['team'].id, 'uuid-marketing')

    def test_whitespace_is_stripped(self):
        module = load_app()
        patch_common(module)
        self.assertEqual(module.resolve_team('fixture-user', '  ENG  ')['team'].id, 'uuid-eng')

    def test_empty_none_and_untyped_targets_are_rejected(self):
        module = load_app()
        patch_common(module)
        for bad in (None, '', '   '):
            with self.subTest(target=bad):
                resolved = module.resolve_team('fixture-user', bad)
                self.assertIn('error', resolved)
                self.assertEqual(resolved['candidates'], [])

    def test_unknown_target_returns_error_without_candidates(self):
        module = load_app()
        patch_common(module)
        resolved = module.resolve_team('fixture-user', 'nonexistent')
        self.assertIn('error', resolved)
        self.assertEqual(resolved['candidates'], [])

    def test_ambiguous_exact_match_lists_candidates(self):
        module = load_app()
        teams = [team('id-1', 'Design', 'DES1'), team('id-2', 'Design', 'DES2')]
        patch_common(module, teams=teams)
        resolved = module.resolve_team('fixture-user', 'design')
        self.assertIn('error', resolved)
        self.assertEqual(len(resolved['candidates']), 2)

    def test_substring_match_is_unique_or_refused(self):
        module = load_app()
        patch_common(module, teams=TEAMS)
        self.assertEqual(module.resolve_team('fixture-user', 'mark')['team'].name, 'Marketing')
        module.get_user_teams = lambda uid: [team('id-1', 'Engineering', 'ENG'), team('id-2', 'Design', 'DES')]
        resolved = module.resolve_team('fixture-user', 'e')  # Engineering AND Design contain 'e'
        self.assertIn('error', resolved)
        self.assertEqual(len(resolved['candidates']), 2)

    def test_no_teams_returns_error(self):
        module = load_app()
        patch_common(module, teams=[])
        resolved = module.resolve_team('fixture-user', 'ENG')
        self.assertIn('error', resolved)


class SanitizeIssueIdentifierTests(unittest.TestCase):
    def test_known_shapes(self):
        module = load_app()
        cases = {
            'ENG-123': 'ENG-123',
            '#ENG-123': 'ENG-123',
            'issue: #ENG-123': 'ENG-123',
            'https://linear.app/workspace/issue/ENG-123/slug': 'ENG-123',
            'eng-123': 'ENG-123',
            '  DES-7  ': 'DES-7',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(module.sanitize_issue_identifier(raw), expected)

    def test_values_without_identifiers_return_none(self):
        module = load_app()
        for raw in (None, '', '   ', 'no identifier here', 123, {'id': 'ENG-1'}, ['ENG-1']):
            with self.subTest(raw=raw):
                self.assertIsNone(module.sanitize_issue_identifier(raw))


class FindStateByNameGuardTests(unittest.TestCase):
    def test_whitespace_and_untyped_status_values_are_rejected(self):
        module = load_app()
        module.get_team_states = Mock(side_effect=AssertionError('must not be called'))
        for bad in ('   ', '', None, 1, ['Done']):
            with self.subTest(state_name=bad):
                state, candidates = module.find_state_by_name('fixture-user', 'team-id', bad)
                self.assertIsNone(state)
                self.assertEqual(candidates, [])


class CreateIssueTeamResolutionTests(unittest.TestCase):
    def run_create(self, body, teams=TEAMS, default=None, states=None):
        module = load_app()
        patch_common(module, teams=teams, default=default)
        if states is not None:
            module.get_team_states = Mock(return_value=states)
        captured = {}

        def graphql(uid, query, variables=None):
            captured['variables'] = variables
            return {'issueCreate': {'success': True, 'issue': dict(
                identifier='ENG-9', title=body.get('title', 't'), url='https://linear.app/x',
                state=dict(name='Todo'))}}

        module.linear_graphql_request = graphql
        response = drive(module, 'tool_create_issue', body)
        return response, captured, module

    def test_no_team_and_multiple_teams_prompts_instead_of_teams0(self):
        response, captured, module = self.run_create({'title': 'hi'})
        self.assertTrue(response.error)
        for fragment in ('Engineering', 'Design', 'Marketing'):
            self.assertIn(fragment, response.error)
        self.assertNotIn('variables', captured, 'must refuse silent mutation')

    def test_no_team_and_single_team_is_used(self):
        solo = [TEAMS[0]]
        response, captured, module = self.run_create({'title': 'hi'}, teams=solo)
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['teamId'], 'uuid-eng')

    def test_default_team_is_honored(self):
        response, captured, module = self.run_create({'title': 'hi'}, default={'id': 'uuid-design'})
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['teamId'], 'uuid-design')

    def test_team_key_resolves_to_uuid(self):
        response, captured, module = self.run_create({'title': 'hi', 'team': 'MKT'})
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['teamId'], 'uuid-marketing')

    def test_team_name_resolves_to_uuid(self):
        response, captured, module = self.run_create({'title': 'hi', 'team': 'Design'})
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['teamId'], 'uuid-design')

    def test_unknown_team_is_refused_with_available_teams(self):
        response, captured, module = self.run_create({'title': 'hi', 'team': 'nope'})
        self.assertTrue(response.error)
        self.assertIn('nope', response.error)
        self.assertNotIn('variables', captured)

    def test_numeric_priority_string_maps_to_int(self):
        response, captured, module = self.run_create({'title': 'hi', 'team': 'ENG', 'priority': '1'})
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['priority'], 1)

    def test_word_priority_still_maps(self):
        response, captured, module = self.run_create({'title': 'hi', 'team': 'ENG', 'priority': 'urgent'})
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['priority'], 1)

    def test_out_of_range_numeric_priority_falls_back_to_none(self):
        response, captured, module = self.run_create({'title': 'hi', 'team': 'ENG', 'priority': '9'})
        self.assertIsNone(response.error)
        self.assertNotIn('priority', captured['variables']['input'])

    def test_status_binds_state_id(self):
        done_state = SimpleNamespace(id='st-done', name='Done', type='completed', position=0)
        response, captured, module = self.run_create(
            {'title': 'hi', 'team': 'ENG', 'status': 'Done'},
            states=[done_state],
        )
        self.assertIsNone(response.error)
        self.assertEqual(captured['variables']['input']['stateId'], 'st-done')


class NullFieldSafetyTests(unittest.TestCase):
    def test_get_issue_with_null_optional_fields_renders_defaults(self):
        module = load_app()
        patch_common(module)
        module.linear_graphql_request = Mock(return_value={'issue': dict(
            id='i1', identifier='ENG-5', title='Nulls everywhere', priority=0, estimate=None,
            state=None, assignee=None, creator=None, team=None, project=None, labels=None,
            url='https://linear.app/x', description=None)})
        response = drive(module, 'tool_get_issue', {'issue_identifier': 'ENG-5'})
        self.assertIsNone(response.error, response.error)
        self.assertIn('Unknown', response.result)
        self.assertIn('No project', response.result)
        self.assertIn('**Labels:** None', response.result)

    def test_update_status_with_null_team_is_a_clean_error(self):
        module = load_app()
        patch_common(module)
        module.linear_graphql_request = Mock(return_value={'issue': dict(
            id='i1', identifier='ENG-5', title='Orphan', team=None, state=None)})
        response = drive(module, 'tool_update_issue_status', {'issue_identifier': 'ENG-5', 'new_status': 'Done'})
        self.assertTrue(response.error)
        self.assertIn('no team', response.error.lower())

    def test_dirty_identifiers_reach_the_lookup_sanitized(self):
        module = load_app()
        patch_common(module)
        seen = {}

        def lookup(uid, ident):
            seen['ident'] = ident
            return {'issue': ISSUE}

        module.get_issue_by_identifier = lookup
        response = drive(module, 'tool_get_issue', {'issue_identifier': 'issue: #eng-123'})
        self.assertIsNone(response.error)
        self.assertEqual(seen['ident'], 'ENG-123')

    def test_identifier_without_any_issue_shape_is_rejected_cleanly(self):
        module = load_app()
        patch_common(module)
        module.get_issue_by_identifier = Mock(side_effect=AssertionError('must not be called'))
        response = drive(module, 'tool_get_issue', {'issue_identifier': 'not an identifier'})
        self.assertTrue(response.error)
        self.assertIn('identifier', response.error.lower())


class ManifestTests(unittest.TestCase):
    def test_create_issue_manifest_declares_team_and_status(self):
        module = load_app()
        tools = asyncio.run(module.get_omi_tools_manifest())['tools']
        create = next(t for t in tools if t['name'] == 'linear_create_issue')
        properties = create['parameters']['properties']
        self.assertIn('team', properties)
        self.assertIn('status', properties)


if __name__ == '__main__':
    unittest.main(verbosity=2)
