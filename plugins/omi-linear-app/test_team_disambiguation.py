"""Hermetic regressions for Linear team, status, and identifier handling.

The suite uses only the standard library and replaces FastAPI, storage, HTTP,
and Pydantic imports with seams.  It executes the production helpers and chat
handlers, so malformed GraphQL shapes cannot be hidden behind source-only
assertions.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock


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
        "fastapi": dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock()),
        "fastapi.responses": dict(HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        "fastapi.staticfiles": dict(StaticFiles=Mock()),
        "fastapi.templating": dict(Jinja2Templates=Mock()),
        "dotenv": dict(load_dotenv=lambda: None),
        "requests": dict(post=Mock(side_effect=AssertionError("Unexpected HTTP")), RequestException=Exception),
        "db": {name: Mock(side_effect=AssertionError("Unexpected storage")) for name in (
            "store_linear_tokens", "get_linear_tokens", "delete_linear_tokens", "is_token_expired",
            "store_default_team", "get_default_team", "get_user_settings",
        )},
        "models": {name: Response if name == "ChatToolResponse" else SimpleNamespace for name in (
            "ChatToolResponse", "LinearIssue", "LinearTeam", "LinearProject", "LinearComment", "LinearUser", "WorkflowState",
        )},
    }
    for name, values in definitions.items():
        modules[name] = ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location(
        "linear_disambiguation_under_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    # Each test gets a fresh module, avoiding state leaking across seams.
    from unittest.mock import patch
    with patch.dict(sys.modules, modules), patch.dict("os.environ", {}, clear=True):
        spec.loader.exec_module(module)
    return module


def team(team_id, name, key):
    return SimpleNamespace(id=team_id, name=name, key=key)


def state(state_id, name, state_type="started", position=0):
    return SimpleNamespace(id=state_id, name=name, type=state_type, color="#888", position=position)


class IdentifierTests(unittest.TestCase):
    def test_shorthand_is_normalized(self):
        module = load_app()
        self.assertEqual(module.sanitize_issue_identifier("  issue: #eng-123. "), "ENG-123")
        self.assertEqual(module.sanitize_issue_identifier("(ENG-123)"), "ENG-123")
        self.assertEqual(module.sanitize_issue_identifier("(issue: ENG-123)"), "ENG-123")

    def test_issue_team_key_is_not_stripped_as_a_prefix(self):
        module = load_app()
        self.assertEqual(module.sanitize_issue_identifier("ISSUE-123"), "ISSUE-123")

    def test_url_is_normalized(self):
        module = load_app()
        self.assertEqual(
            module.sanitize_issue_identifier("https://linear.app/acme/issue/eng-123/fix-login?focus=1"),
            "ENG-123",
        )

    def test_dirty_non_string_values_are_rejected(self):
        module = load_app()
        for raw in (None, 123, {}, [], "", "   ", "ENG123", "issue: #ENG-nope", "https://linear.app/acme/ENG-123"):
            with self.subTest(raw=raw):
                self.assertIsNone(module.sanitize_issue_identifier(raw))

    def test_invalid_identifier_never_reaches_graphql(self):
        module = load_app()
        module.linear_graphql_request = Mock()
        self.assertEqual(module.get_issue_by_identifier("u", "not an issue"), {"error": "Invalid Linear issue identifier"})
        module.linear_graphql_request.assert_not_called()

    def test_issue_lookup_uses_only_sanitized_identifier(self):
        module = load_app()
        module.linear_graphql_request = Mock(return_value={"issue": None})
        module.get_issue_by_identifier("u", "issue: #eng-123")
        self.assertEqual(module.linear_graphql_request.call_args.args[2], {"id": "ENG-123"})


class NullableGraphqlTests(unittest.TestCase):
    def test_nullable_team_connection_is_empty(self):
        module = load_app()
        module.linear_graphql_request = lambda *args, **kwargs: {"teams": None}
        self.assertEqual(module.get_user_teams("u"), [])

    def test_nullable_state_connection_is_empty(self):
        module = load_app()
        module.linear_graphql_request = lambda *args, **kwargs: {"team": {"states": None}}
        self.assertEqual(module.get_team_states("u", "t"), [])

    def test_null_nodes_connection_is_empty(self):
        module = load_app()
        module.linear_graphql_request = lambda *args, **kwargs: {"teams": {"nodes": None}}
        self.assertEqual(module.get_user_teams("u"), [])
        module.linear_graphql_request = lambda *args, **kwargs: {"team": {"states": {"nodes": None}}}
        self.assertEqual(module.get_team_states("u", "t"), [])

    def test_malformed_nodes_are_skipped(self):
        module = load_app()
        module.linear_graphql_request = lambda *args, **kwargs: {"teams": {"nodes": [None, {}, {"id": "t", "name": "Eng", "key": "ENG"}]}}
        self.assertEqual([t.id for t in module.get_user_teams("u")], ["t"])
        module.linear_graphql_request = lambda *args, **kwargs: {"team": {"states": {"nodes": [None, {"id": "s", "name": "Todo", "type": "unstarted"}]}}}
        self.assertEqual([s.id for s in module.get_team_states("u", "t")], ["s"])

    def test_get_issue_formats_nullable_optional_fields(self):
        module = load_app()
        module.get_linear_tokens = lambda uid: True
        module.linear_graphql_request = lambda *args, **kwargs: {
            "issue": {"id": "i", "identifier": "ENG-1", "title": "Null-safe", "priority": 0,
                      "state": None, "assignee": None, "creator": None, "team": None,
                      "project": None, "labels": None, "url": "https://linear.app/acme/issue/ENG-1"}
        }

        async def body():
            return {"uid": "u", "issue_identifier": "#eng-1"}

        response = asyncio.run(module.tool_get_issue(SimpleNamespace(json=body)))
        self.assertIsNone(response.error)
        self.assertIn("Unassigned", response.result)

    def test_update_status_fails_cleanly_without_team(self):
        module = load_app()
        module.get_linear_tokens = lambda uid: True
        module.linear_graphql_request = lambda *args, **kwargs: {
            "issue": {"id": "i", "identifier": "ENG-1", "title": "No team", "team": None}
        }
        module.find_state_by_name = Mock()

        async def body():
            return {"uid": "u", "issue_identifier": "ENG-1", "new_status": "Done"}

        response = asyncio.run(module.tool_update_issue_status(SimpleNamespace(json=body)))
        self.assertIsNotNone(response.error)
        module.find_state_by_name.assert_not_called()


class TeamResolutionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_app()
        self.teams = [team("uuid-a", "Alpha Engineering", "ENG"), team("uuid-b", "Beta Engineering", "OPS")]
        self.module.get_user_teams = lambda uid: self.teams
        self.module.get_default_team = lambda uid: None

    def test_single_team_without_target_is_safe(self):
        self.module.get_user_teams = lambda uid: [self.teams[0]]
        resolved, candidates = self.module.resolve_team("u")
        self.assertEqual(resolved.id, "uuid-a")
        self.assertEqual(candidates, [self.teams[0]])

    def test_multiple_teams_without_target_are_ambiguous(self):
        resolved, candidates = self.module.resolve_team("u")
        self.assertIsNone(resolved)
        self.assertEqual([t.id for t in candidates], ["uuid-a", "uuid-b"])

    def test_saved_default_wins_without_target(self):
        self.module.get_default_team = lambda uid: {"id": "uuid-b", "name": "Beta Engineering"}
        resolved, candidates = self.module.resolve_team("u")
        self.assertEqual(resolved.id, "uuid-b")
        self.assertEqual(candidates, [self.teams[1]])

    def test_uuid_tier_wins(self):
        resolved, _ = self.module.resolve_team("u", "UUID-A")
        self.assertEqual(resolved.id, "uuid-a")

    def test_exact_key_or_name_tier(self):
        self.assertEqual(self.module.resolve_team("u", "ops")[0].id, "uuid-b")
        self.assertEqual(self.module.resolve_team("u", "Alpha Engineering")[0].id, "uuid-a")

    def test_unique_substring_tier(self):
        self.assertEqual(self.module.resolve_team("u", "Alpha")[0].id, "uuid-a")

    def test_ambiguous_substring_never_selects_first(self):
        resolved, candidates = self.module.resolve_team("u", "Engineering")
        self.assertIsNone(resolved)
        self.assertEqual([t.id for t in candidates], ["uuid-a", "uuid-b"])

    def test_non_string_target_is_safe(self):
        resolved, candidates = self.module.resolve_team("u", {"team": "ENG"})
        self.assertIsNone(resolved)
        self.assertEqual(candidates, [])


class StateAndCreateTests(unittest.TestCase):
    def test_blank_or_non_string_state_is_rejected(self):
        module = load_app()
        module.get_team_states = Mock(return_value=[state("s", "Done", "completed")])
        for raw in (None, 0, {}, "", "   "):
            with self.subTest(raw=raw):
                resolved, candidates = module.find_state_by_name("u", "t", raw)
                self.assertIsNone(resolved)
                self.assertEqual(candidates, [])
        module.get_team_states.assert_not_called()

    def test_state_alias_and_ambiguous_partial(self):
        module = load_app()
        module.get_team_states = lambda uid, team_id: [state("a", "In Review"), state("b", "Peer Review")]
        self.assertIsNone(module.find_state_by_name("u", "t", "review")[0])
        module.get_team_states = lambda uid, team_id: [state("s", "Shipped", "completed")]
        self.assertEqual(module.find_state_by_name("u", "t", "done")[0].id, "s")

    def test_create_binds_team_status_and_numeric_priority(self):
        module = load_app()
        module.get_linear_tokens = lambda uid: True
        selected = team("uuid-a", "Alpha", "ENG")
        selected_state = state("done-id", "Done", "completed")
        module.resolve_team = Mock(return_value=(selected, [selected]))
        module.find_state_by_name = Mock(return_value=(selected_state, [selected_state]))
        calls = []

        def graphql(uid, query, variables=None):
            calls.append((query, variables))
            return {"issueCreate": {"success": True, "issue": {"identifier": "ENG-9", "url": "url", "state": None}}}

        module.linear_graphql_request = graphql

        async def body():
            return {"uid": "u", "title": "Test", "team": "ENG", "status": "Done", "priority": "2"}

        response = asyncio.run(module.tool_create_issue(SimpleNamespace(json=body)))
        self.assertIsNone(response.error)
        self.assertEqual(calls[0][1]["input"], {"teamId": "uuid-a", "title": "Test", "priority": 2, "stateId": "done-id"})
        module.resolve_team.assert_called_once_with("u", "ENG")
        module.find_state_by_name.assert_called_once_with("u", "uuid-a", "Done")

    def test_create_refuses_ambiguous_team_without_mutating(self):
        module = load_app()
        module.get_linear_tokens = lambda uid: True
        candidates = [team("a", "Alpha", "ENG"), team("b", "Beta", "ENG2")]
        module.resolve_team = Mock(return_value=(None, candidates))
        module.linear_graphql_request = Mock()

        async def body():
            return {"uid": "u", "title": "Test", "team": "Eng"}

        response = asyncio.run(module.tool_create_issue(SimpleNamespace(json=body)))
        self.assertIsNone(response.result)
        self.assertIn("ambiguous", response.error)
        module.linear_graphql_request.assert_not_called()

    def test_create_refuses_multiple_teams_without_default(self):
        module = load_app()
        module.get_linear_tokens = lambda uid: True
        module.resolve_team = Mock(return_value=(None, [team("a", "Alpha", "ENG"), team("b", "Beta", "OPS")]))
        module.linear_graphql_request = Mock()

        async def body():
            return {"uid": "u", "title": "Test"}

        response = asyncio.run(module.tool_create_issue(SimpleNamespace(json=body)))
        self.assertIn("Multiple Linear teams", response.error)
        module.linear_graphql_request.assert_not_called()

    def test_create_refuses_ambiguous_status_without_mutating(self):
        module = load_app()
        module.get_linear_tokens = lambda uid: True
        selected = team("uuid-a", "Alpha", "ENG")
        module.resolve_team = Mock(return_value=(selected, [selected]))
        module.find_state_by_name = Mock(return_value=(None, [state("a", "In Review"), state("b", "Peer Review")]))
        module.linear_graphql_request = Mock()

        async def body():
            return {"uid": "u", "title": "Test", "status": "review"}

        response = asyncio.run(module.tool_create_issue(SimpleNamespace(json=body)))
        self.assertIn("ambiguous", response.error)
        module.linear_graphql_request.assert_not_called()

    def test_manifest_declares_team_and_status(self):
        module = load_app()
        manifest = asyncio.run(module.get_omi_tools_manifest())
        create = next(tool for tool in manifest["tools"] if tool["name"] == "linear_create_issue")
        properties = create["parameters"]["properties"]
        self.assertIn("team", properties)
        self.assertIn("status", properties)

    def test_model_source_declares_create_issue_aliases(self):
        source = Path(__file__).with_name("models.py").read_text(encoding="utf-8")
        self.assertRegex(source, r"class CreateIssueRequest[\s\S]*team: Optional\[str\]")
        self.assertRegex(source, r"class CreateIssueRequest[\s\S]*status: Optional\[str\]")


if __name__ == "__main__":
    unittest.main()
