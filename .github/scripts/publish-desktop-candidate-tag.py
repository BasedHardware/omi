#!/usr/bin/env python3
"""Atomically publish an annotated macOS candidate tag against live main."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ZERO_OID = "0" * 40
TAGGER_NAME = "github-actions[bot]"
TAGGER_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

REPOSITORY_ID_QUERY = """
query RepositoryId($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) { id }
}
"""

UPDATE_REFS_MUTATION = """
mutation PublishCandidateTag(
  $repositoryId: ID!,
  $mainBefore: GitObjectID!,
  $mainAfter: GitObjectID!,
  $tagName: GitRefname!,
  $tagObject: GitObjectID!,
  $zeroOid: GitObjectID!
) {
  updateRefs(input: {
    repositoryId: $repositoryId,
    refUpdates: [
      {
        name: "refs/heads/main",
        beforeOid: $mainBefore,
        afterOid: $mainAfter,
        force: false
      },
      {
        name: $tagName,
        beforeOid: $zeroOid,
        afterOid: $tagObject,
        force: false
      }
    ]
  }) {
    clientMutationId
  }
}
"""


def run_gh_json(args: list[str], payload: dict[str, object]) -> dict[str, object]:
    """Call the authenticated GitHub CLI without exposing structured input to a shell."""
    result = subprocess.run(
        ["gh", *args, "--input", "-"],
        check=True,
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        decoded = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("GitHub API returned invalid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("GitHub API returned an unexpected JSON payload")
    if decoded.get("errors"):
        raise ValueError(f"GitHub GraphQL rejected the ref transaction: {decoded['errors']}")
    return decoded


def repository_id(repository: str) -> str:
    owner, separator, name = repository.partition("/")
    if not owner or not separator or not name or "/" in name:
        raise ValueError("repository must be in owner/name form")
    response = run_gh_json(
        ["api", "graphql"],
        {"query": REPOSITORY_ID_QUERY, "variables": {"owner": owner, "name": name}},
    )
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("repository"), dict):
        raise ValueError("GitHub did not return a repository node")
    identifier = data["repository"].get("id")
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("GitHub did not return a repository ID")
    return identifier


def create_annotated_tag_object(
    *, repository: str, release_tag: str, candidate_sha: str, evidence: str, timestamp: str
) -> str:
    response = run_gh_json(
        ["api", "--method", "POST", f"repos/{repository}/git/tags"],
        {
            "tag": release_tag,
            "message": evidence,
            "object": candidate_sha,
            "type": "commit",
            "tagger": {"name": TAGGER_NAME, "email": TAGGER_EMAIL, "date": timestamp},
        },
    )
    tag_object_sha = response.get("sha")
    if not isinstance(tag_object_sha, str) or len(tag_object_sha) != 40:
        raise ValueError("GitHub did not return the annotated tag object SHA")
    return tag_object_sha


def atomic_publish_tag_ref(
    *, repository_id_value: str, release_tag: str, candidate_sha: str, tag_object_sha: str
) -> None:
    """Publish only if live main still points at the identity-validated SHA.

    GitHub's `updateRefs` mutation evaluates every `beforeOid` and applies all
    ref updates as one transaction. Keeping main unchanged still makes its
    current OID a server-enforced precondition for adding the immutable tag.
    """
    run_gh_json(
        ["api", "graphql"],
        {
            "query": UPDATE_REFS_MUTATION,
            "variables": {
                "repositoryId": repository_id_value,
                "mainBefore": candidate_sha,
                "mainAfter": candidate_sha,
                "tagName": f"refs/tags/{release_tag}",
                "tagObject": tag_object_sha,
                "zeroOid": ZERO_OID,
            },
        },
    )


def publish_candidate_tag(*, repository: str, release_tag: str, candidate_sha: str, evidence: str, timestamp: str) -> None:
    repo_id = repository_id(repository)
    # A tag object alone is unreachable and is not a candidate. The only
    # candidate-creating action is the atomic ref transaction below.
    tag_object_sha = create_annotated_tag_object(
        repository=repository,
        release_tag=release_tag,
        candidate_sha=candidate_sha,
        evidence=evidence,
        timestamp=timestamp,
    )
    atomic_publish_tag_ref(
        repository_id_value=repo_id,
        release_tag=release_tag,
        candidate_sha=candidate_sha,
        tag_object_sha=tag_object_sha,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence.read_text(encoding="utf-8")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    publish_candidate_tag(
        repository=args.repository,
        release_tag=args.release_tag,
        candidate_sha=args.candidate_sha,
        evidence=evidence,
        timestamp=timestamp,
    )
    print(f"Published immutable candidate tag {args.release_tag} at {args.candidate_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
