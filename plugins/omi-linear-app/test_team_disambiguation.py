"""Hermetic unit tests for Linear team resolution, issue identifier sanitization, and reliability hardening."""
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
            'ChatToolResponse', 'LinearIssue', 'LinearTeam', 'LinearProject', 'LinearComment', 'LinearUser', 'WorkflowState', 'LinearLabel')},
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location('linear_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {}, clear=True):
        spec.loader.exec_module(module)
    return module


TEAM_ENG = SimpleNamespace(id='uuid-team-eng', name='Engineering', key='ENG', description='Core Engineering')
TEAM_MOB = SimpleNamespace(id='uuid-team-mob', name='Mobile App', key='MOB', description='iOS & Android')
TEAM_DES = SimpleNamespace(id='uuid-team-des', name='Design', key='DES', description='Product Design')

STATE_TODO = SimpleNamespace(id='state-todo-id', name='Todo', type='unstarted', color='#888', position=0)
STATE_IN_PROG = SimpleNamespace(id='state-prog-id', name='In Progress', type='started', color='#888', position=1)
STATE_DONE = SimpleNamespace(id='state-done-id', name='Done', type='completed', color='#888', position=2)

ISSUE = dict(
    id='issue-uuid-123',
    identifier='ENG-123',
    title='Core issue',
    url='https://linear.app/test/issue/ENG-123',
    team=dict(id='uuid-team-eng', name='Engineering'),
    state=dict(name='Todo'),
    labels=dict(nodes=[])
)


class LinearTeamDisambiguationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_app()

    def test_sanitize_issue_identifier_valid_and_dirty_inputs(self):
        sanitize = self.module.sanitize_issue_identifier

        # Standard clean shorthand
        self.assertEqual(sanitize('ENG-123'), 'ENG-123')
        self.assertEqual(sanitize('eng-123'), 'ENG-123')
        self.assertEqual(sanitize('  ENG-123  '), 'ENG-123')

        # Prefix stripping (# or issue:)
        self.assertEqual(sanitize('#ENG-123'), 'ENG-123')
        self.assertEqual(sanitize('###ENG-123'), 'ENG-123')
        self.assertEqual(sanitize('issue: ENG-123'), 'ENG-123')
        self.assertEqual(sanitize('ISSUE: eng-456'), 'ENG-456')

        # Linear URL extraction
        self.assertEqual(
            sanitize('https://linear.app/my-workspace/issue/ENG-123/fix-login-crash'),
            'ENG-123'
        )
        self.assertEqual(
            sanitize('https://linear.app/issue/MOB-999'),
            'MOB-999'
        )
        self.assertEqual(
            sanitize('http://localhost/issue/FE-42/title'),
            'FE-42'
        )

        # UUID format
        uuid_str = '12345678-1234-1234-1234-123456789abc'
        self.assertEqual(sanitize(uuid_str), uuid_str.upper())

        # Numeric dirty inputs without team prefix are rejected safely as invalid
        self.assertIsNone(sanitize(123))
        self.assertIsNone(sanitize(42.0))

        # Invalid/empty/none inputs
        self.assertIsNone(sanitize(None))
        self.assertIsNone(sanitize(''))
        self.assertIsNone(sanitize('   '))
        self.assertIsNone(sanitize([]))
        self.assertIsNone(sanitize({}))

    def test_resolve_team_by_uuid(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        team, candidates, err = self.module.resolve_team('uid-1', 'uuid-team-eng')
        self.assertEqual(team.id, 'uuid-team-eng')
        self.assertEqual(team.name, 'Engineering')
        self.assertIsNone(err)

    def test_resolve_team_by_key_case_insensitive(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        team, candidates, err = self.module.resolve_team('uid-1', 'eng')
        self.assertEqual(team.id, 'uuid-team-eng')
        self.assertIsNone(err)

        team2, _, _ = self.module.resolve_team('uid-1', 'MOB')
        self.assertEqual(team2.id, 'uuid-team-mob')

    def test_resolve_team_by_name_exact(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        team, candidates, err = self.module.resolve_team('uid-1', 'engineering')
        self.assertEqual(team.id, 'uuid-team-eng')
        self.assertIsNone(err)

    def test_resolve_team_by_partial_match(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB, TEAM_DES])
        # 'design' partially matches 'Design'
        team, candidates, err = self.module.resolve_team('uid-1', 'Des')
        self.assertEqual(team.id, 'uuid-team-des')
        self.assertIsNone(err)

    def test_resolve_team_ambiguous_partial_refused(self):
        team_mob_ios = SimpleNamespace(id='uuid-ios', name='Mobile iOS', key='MIOS')
        team_mob_and = SimpleNamespace(id='uuid-and', name='Mobile Android', key='MAND')
        self.module.get_user_teams = Mock(return_value=[team_mob_ios, team_mob_and])

        team, candidates, err = self.module.resolve_team('uid-1', 'Mobile')
        self.assertIsNone(team)
        self.assertEqual(len(candidates), 2)
        self.assertIn('is ambiguous between teams', err)
        self.assertIn('Mobile iOS', err)
        self.assertIn('Mobile Android', err)

    def test_resolve_team_no_target_uses_default_team(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        self.module.get_default_team = Mock(return_value={'id': 'uuid-team-mob', 'name': 'Mobile App'})

        team, candidates, err = self.module.resolve_team('uid-1', None)
        self.assertEqual(team.id, 'uuid-team-mob')
        self.assertIsNone(err)

    def test_resolve_team_no_target_single_team_auto_selects(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG])
        self.module.get_default_team = Mock(return_value=None)

        team, candidates, err = self.module.resolve_team('uid-1', None)
        self.assertEqual(team.id, 'uuid-team-eng')
        self.assertIsNone(err)

    def test_resolve_team_no_target_multiple_teams_refuses_silent_pick(self):
        # Regression guard: must not silently pick teams[0] when multiple teams exist and no default is set
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        self.module.get_default_team = Mock(return_value=None)

        team, candidates, err = self.module.resolve_team('uid-1', None)
        self.assertIsNone(team)
        self.assertEqual(len(candidates), 2)
        self.assertIn('Multiple teams found', err)

    def test_resolve_team_unknown_target_returns_error(self):
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        team, candidates, err = self.module.resolve_team('uid-1', 'DevOps')
        self.assertIsNone(team)
        self.assertEqual(candidates, [])
        self.assertIn("Could not find team 'DevOps'", err)

    def test_tool_create_issue_resolves_team_key_and_state(self):
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            if 'mutation CreateIssue' in query:
                return {
                    'issueCreate': {
                        'success': True,
                        'issue': {
                            'id': 'new-issue-id',
                            'identifier': 'ENG-456',
                            'title': 'New bug',
                            'url': 'https://linear.app/issue/ENG-456',
                            'state': {'name': 'In Progress'}
                        }
                    }
                }
            return {}

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        self.module.get_default_team = Mock(return_value=None)
        self.module.get_team_states = Mock(return_value=[STATE_TODO, STATE_IN_PROG, STATE_DONE])

        async def json():
            return {
                'uid': 'fixture-user',
                'title': 'New bug',
                'description': 'Crash details',
                'team_id': 'eng',  # Provided team key instead of UUID!
                'status': 'in progress',
                'priority': 'high'
            }

        response = asyncio.run(self.module.tool_create_issue(SimpleNamespace(json=json)))
        self.assertIsNone(response.error)
        self.assertIn('ENG-456', response.result)
        self.assertIn('Team: Engineering', response.result)
        self.assertIn('Status: In Progress', response.result)

        # Assert GraphQL mutation bound the resolved team's UUID, priority=2, and stateId
        create_calls = [c for c in graphql_calls if 'mutation CreateIssue' in c[0]]
        self.assertEqual(len(create_calls), 1)
        mutation_vars = create_calls[0][1]['input']
        self.assertEqual(mutation_vars['teamId'], 'uuid-team-eng')  # Converted from 'eng' to UUID!
        self.assertEqual(mutation_vars['title'], 'New bug')
        self.assertEqual(mutation_vars['description'], 'Crash details')
        self.assertEqual(mutation_vars['priority'], 2)
        self.assertEqual(mutation_vars['stateId'], 'state-prog-id')

    def test_tool_create_issue_ambiguous_team_aborts_mutation(self):
        team_mob_ios = SimpleNamespace(id='uuid-ios', name='Mobile iOS', key='MIOS')
        team_mob_and = SimpleNamespace(id='uuid-and', name='Mobile Android', key='MAND')
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            return {}

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True
        self.module.get_user_teams = Mock(return_value=[team_mob_ios, team_mob_and])
        self.module.get_default_team = Mock(return_value=None)

        async def json():
            return {
                'uid': 'fixture-user',
                'title': 'New bug',
                'team_id': 'Mobile'
            }

        response = asyncio.run(self.module.tool_create_issue(SimpleNamespace(json=json)))
        self.assertIsNotNone(response.error)
        self.assertIn('ambiguous between teams', response.error)
        self.assertEqual(len(graphql_calls), 0)  # No mutation executed

    def test_handlers_survive_dirty_and_url_issue_identifiers(self):
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            if 'mutation UpdateIssue' in query:
                return {'issueUpdate': {'success': True, 'issue': {'state': {'name': 'Done'}}}}
            if 'mutation CreateComment' in query:
                return {'commentCreate': {'success': True}}
            return {'issue': ISSUE}

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True
        self.module.get_team_states = Mock(return_value=[STATE_TODO, STATE_DONE])

        # 1. tool_get_issue with full Linear URL
        async def json_get():
            return {
                'uid': 'fixture-user',
                'issue_identifier': 'https://linear.app/my-workspace/issue/ENG-123/some-slug'
            }

        resp_get = asyncio.run(self.module.tool_get_issue(SimpleNamespace(json=json_get)))
        self.assertIsNone(resp_get.error)
        self.assertIn('ENG-123', resp_get.result)

        # 2. tool_update_issue_status with leading #
        async def json_update():
            return {
                'uid': 'fixture-user',
                'issue_identifier': '#ENG-123',
                'new_status': 'Done'
            }

        resp_update = asyncio.run(self.module.tool_update_issue_status(SimpleNamespace(json=json_update)))
        self.assertIsNone(resp_update.error)
        self.assertIn('ENG-123', resp_update.result)

        # 3. tool_add_comment with clean shorthand
        async def json_comment():
            return {
                'uid': 'fixture-user',
                'issue_identifier': 'ENG-123',
                'comment': 'Looks good!'
            }

        resp_comment = asyncio.run(self.module.tool_add_comment(SimpleNamespace(json=json_comment)))
        self.assertIsNone(resp_comment.error)
        self.assertIn('Looks good!', resp_comment.result)

        # 4. None / missing identifier returns clear error without crashing
        async def json_null():
            return {
                'uid': 'fixture-user',
                'issue_identifier': None
            }

        resp_null = asyncio.run(self.module.tool_get_issue(SimpleNamespace(json=json_null)))
        self.assertIsNotNone(resp_null.error)
        self.assertIn('Issue identifier is required', resp_null.error)

    def test_find_state_by_name_whitespace_only_returns_none(self):
        self.module.get_team_states = Mock(return_value=[STATE_TODO, STATE_IN_PROG, STATE_DONE])
        state, candidates = self.module.find_state_by_name('uid-1', 'team-id', '   ')
        self.assertIsNone(state)
        self.assertEqual(candidates, [])

        state_empty, candidates_empty = self.module.find_state_by_name('uid-1', 'team-id', '')
        self.assertIsNone(state_empty)
        self.assertEqual(candidates_empty, [])

        state_none, candidates_none = self.module.find_state_by_name('uid-1', 'team-id', None)
        self.assertIsNone(state_none)
        self.assertEqual(candidates_none, [])

        state_num, candidates_num = self.module.find_state_by_name('uid-1', 'team-id', 999)
        self.assertIsNone(state_num)
        self.assertEqual(candidates_num, [])

    def test_tool_create_issue_blank_title_rejected(self):
        self.module.get_linear_tokens = lambda uid: True
        self.module.linear_graphql_request = Mock(side_effect=AssertionError("Should not call GraphQL"))

        async def json_blank():
            return {
                'uid': 'fixture-user',
                'title': '   ',
            }

        resp = asyncio.run(self.module.tool_create_issue(SimpleNamespace(json=json_blank)))
        self.assertIsNotNone(resp.error)
        self.assertIn('cannot be empty', resp.error)

    def test_tool_create_issue_accepts_team_alias(self):
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            return {
                'issueCreate': {
                    'success': True,
                    'issue': {
                        'id': 'new-issue-id',
                        'identifier': 'ENG-789',
                        'title': 'Alias bug',
                        'url': 'https://linear.app/issue/ENG-789',
                        'state': {'name': 'Todo'}
                    }
                }
            }

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG, TEAM_MOB])
        self.module.get_default_team = Mock(return_value=None)

        async def json_team_alias():
            return {
                'uid': 'fixture-user',
                'title': 'Alias bug',
                'team': 'eng'  # Using 'team' alias
            }

        resp = asyncio.run(self.module.tool_create_issue(SimpleNamespace(json=json_team_alias)))
        self.assertIsNone(resp.error)
        self.assertIn('ENG-789', resp.result)
        self.assertIn('Team: Engineering', resp.result)
        create_call = [c for c in graphql_calls if 'mutation CreateIssue' in c[0]][0]
        self.assertEqual(create_call[1]['input']['teamId'], 'uuid-team-eng')

    def test_tool_get_issue_survives_null_graphql_fields(self):
        # Linear GraphQL returns null for optional fields
        null_issue = {
            'id': 'issue-uuid-null',
            'identifier': 'ENG-999',
            'title': 'Issue with null fields',
            'state': None,
            'assignee': None,
            'creator': None,
            'team': None,
            'project': None,
            'labels': None,
            'url': None,
        }
        self.module.linear_graphql_request = Mock(return_value={'issue': null_issue})
        self.module.get_linear_tokens = lambda uid: True

        async def json_get():
            return {
                'uid': 'fixture-user',
                'issue_identifier': 'ENG-999'
            }

        resp = asyncio.run(self.module.tool_get_issue(SimpleNamespace(json=json_get)))
        self.assertIsNone(resp.error)
        self.assertIn('ENG-999', resp.result)
        self.assertIn('Unknown', resp.result)
        self.assertIn('Unassigned', resp.result)

    def test_tool_update_issue_status_survives_missing_or_null_team(self):
        # When issue GraphQL response has team: None
        issue_no_team = {
            'id': 'issue-uuid-no-team',
            'identifier': 'ENG-100',
            'title': 'Issue without team',
            'team': None
        }
        self.module.linear_graphql_request = Mock(return_value={'issue': issue_no_team})
        self.module.get_linear_tokens = lambda uid: True

        async def json_update():
            return {
                'uid': 'fixture-user',
                'issue_identifier': 'ENG-100',
                'new_status': 'Done'
            }

        resp = asyncio.run(self.module.tool_update_issue_status(SimpleNamespace(json=json_update)))
        self.assertIsNotNone(resp.error)
        self.assertIn('Could not determine team', resp.error)

    def test_get_user_teams_and_states_survive_null_nodes(self):
        # When GraphQL returns {"teams": {"nodes": None}}
        self.module.linear_graphql_request = Mock(return_value={'teams': {'nodes': None}})
        teams = self.module.get_user_teams('uid-1')
        self.assertEqual(teams, [])

        # When GraphQL returns {"team": {"states": {"nodes": None}}}
        self.module.linear_graphql_request = Mock(return_value={'team': {'states': {'nodes': None}}})
        states = self.module.get_team_states('uid-1', 'team-id')
        self.assertEqual(states, [])

    def test_tool_create_issue_string_numeric_priority(self):
        graphql_calls = []

        def fake_graphql(uid, query, variables=None):
            graphql_calls.append((query, variables))
            return {
                'issueCreate': {
                    'success': True,
                    'issue': {
                        'id': 'new-issue-id',
                        'identifier': 'ENG-500',
                        'title': 'Priority test',
                        'url': 'https://linear.app/issue/ENG-500',
                        'state': None  # Also tests null state in created issue!
                    }
                }
            }

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True
        self.module.get_user_teams = Mock(return_value=[TEAM_ENG])
        self.module.get_default_team = Mock(return_value=None)

        async def json_priority():
            return {
                'uid': 'fixture-user',
                'title': 'Priority test',
                'priority': '2'  # String numeric
            }

        resp = asyncio.run(self.module.tool_create_issue(SimpleNamespace(json=json_priority)))
        self.assertIsNone(resp.error)
        self.assertIn('ENG-500', resp.result)
        self.assertIn('Status: Unknown', resp.result)  # Handled null state gracefully
        create_call = [c for c in graphql_calls if 'mutation CreateIssue' in c[0]][0]
        self.assertEqual(create_call[1]['input']['priority'], 2)

    def test_tool_update_issue_status_survives_null_state(self):
        # Test updated_issue with state: None
        def fake_graphql(uid, query, variables=None):
            if 'mutation UpdateIssue' in query:
                return {
                    'issueUpdate': {
                        'success': True,
                        'issue': {
                            'id': 'issue-uuid-123',
                            'identifier': 'ENG-123',
                            'state': None
                        }
                    }
                }
            return {'issue': ISSUE}

        self.module.linear_graphql_request = fake_graphql
        self.module.get_linear_tokens = lambda uid: True
        self.module.get_team_states = Mock(return_value=[STATE_TODO, STATE_DONE])

        async def json_update():
            return {
                'uid': 'fixture-user',
                'issue_identifier': 'ENG-123',
                'new_status': 'Done'
            }

        resp = asyncio.run(self.module.tool_update_issue_status(SimpleNamespace(json=json_update)))
        self.assertIsNone(resp.error)
        self.assertIn('Updated **ENG-123** to **Done**', resp.result)

    def test_sanitize_issue_identifier_spaced_hashes(self):
        sanitize = self.module.sanitize_issue_identifier
        self.assertEqual(sanitize('# # ENG-123'), 'ENG-123')
        self.assertEqual(sanitize('### # ENG-999'), 'ENG-999')
        self.assertEqual(sanitize('issue: # ENG-456'), 'ENG-456')


if __name__ == '__main__':
    unittest.main()


