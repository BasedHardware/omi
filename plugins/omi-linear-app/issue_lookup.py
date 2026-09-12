"""Exact Linear issue lookup for identifier-targeted chat tools.

``searchIssues(term:, first: 1)`` can return a *different* issue (ENG-1234
when the user asked for ENG-123). Linear's ``issue(id:)`` accepts the
shorthand identifier and is exact.
"""

from typing import Any, Callable, Dict

ISSUE_BY_ID_QUERY = """
query($id: String!) {
    issue(id: $id) {
        id
        identifier
        title
        description
        priority
        estimate
        url
        createdAt
        updatedAt
        state {
            name
            type
        }
        assignee {
            name
        }
        creator {
            name
        }
        team {
            id
            name
        }
        project {
            name
        }
        labels {
            nodes {
                name
            }
        }
    }
}
"""


def resolve_issue_by_identifier(
    graphql_fn: Callable[..., Dict[str, Any]],
    uid: str,
    identifier: str,
) -> Dict[str, Any]:
    """Return ``{"issue": ...}`` or ``{"error": ...}``. Never uses searchIssues."""
    ident = (identifier or "").strip()
    if not ident:
        return {"error": "Issue identifier is required (e.g., ENG-123)"}

    wanted = ident.upper()
    result = graphql_fn(uid, ISSUE_BY_ID_QUERY, {"id": wanted})
    if "error" in result:
        err = str(result["error"])
        lowered = err.lower()
        if "not found" in lowered or "could not find" in lowered:
            return {"error": f"Could not find issue: {identifier}"}
        return {"error": err}

    issue = result.get("issue")
    if not issue:
        return {"error": f"Could not find issue: {identifier}"}

    got = (issue.get("identifier") or "").upper()
    if got and got != wanted:
        return {"error": f"Could not find issue: {identifier}"}

    return {"issue": issue}
