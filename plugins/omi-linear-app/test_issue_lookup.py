"""Hermetic tests for exact Linear issue lookup (#13162).

No network, Linear credentials, FastAPI, or Redis. The production
``searchIssues(term:, first: 1)`` path is never used.
"""

import unittest

import issue_lookup


class ResolveIssueByIdentifierTests(unittest.TestCase):
    def test_uses_issue_id_query_not_searchissues(self):
        captured = {}

        def fake_graphql(uid, query, variables=None):
            captured["uid"] = uid
            captured["query"] = query
            captured["variables"] = variables
            return {
                "issue": {
                    "id": "uuid-123",
                    "identifier": "ENG-123",
                    "title": "Exact",
                    "team": {"id": "team-1", "name": "Eng"},
                }
            }

        result = issue_lookup.resolve_issue_by_identifier(
            fake_graphql, "user-1", "eng-123"
        )
        self.assertEqual(result["issue"]["id"], "uuid-123")
        self.assertIn("issue(id: $id)", captured["query"])
        self.assertNotIn("searchIssues", captured["query"])
        self.assertEqual(captured["variables"], {"id": "ENG-123"})
        self.assertEqual(captured["uid"], "user-1")

    def test_prefix_hit_from_search_would_be_rejected_here(self):
        def fake_graphql(uid, query, variables=None):
            return {
                "issue": {
                    "id": "uuid-1234",
                    "identifier": "ENG-1234",
                    "title": "Wrong neighbour",
                    "team": {"id": "team-1", "name": "Eng"},
                }
            }

        result = issue_lookup.resolve_issue_by_identifier(
            fake_graphql, "user-1", "ENG-123"
        )
        self.assertEqual(result["error"], "Could not find issue: ENG-123")

    def test_missing_issue_is_not_found(self):
        def fake_graphql(uid, query, variables=None):
            return {"issue": None}

        result = issue_lookup.resolve_issue_by_identifier(
            fake_graphql, "user-1", "ENG-123"
        )
        self.assertEqual(result["error"], "Could not find issue: ENG-123")

    def test_entity_not_found_graphql_error(self):
        def fake_graphql(uid, query, variables=None):
            return {"error": "Entity not found: Issue"}

        result = issue_lookup.resolve_issue_by_identifier(
            fake_graphql, "user-1", "ENG-123"
        )
        self.assertEqual(result["error"], "Could not find issue: ENG-123")

    def test_transport_error_is_passed_through(self):
        def fake_graphql(uid, query, variables=None):
            return {"error": "Request failed: timeout"}

        result = issue_lookup.resolve_issue_by_identifier(
            fake_graphql, "user-1", "ENG-123"
        )
        self.assertEqual(result["error"], "Request failed: timeout")

    def test_empty_identifier(self):
        def fake_graphql(*_a, **_k):
            self.fail("must not call GraphQL")

        result = issue_lookup.resolve_issue_by_identifier(fake_graphql, "user-1", "  ")
        self.assertIn("Issue identifier is required", result["error"])


if __name__ == "__main__":
    unittest.main()
