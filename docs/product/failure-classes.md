# Failure-class registry

Definitions live in `.github/failure-classes/FC-<slug>.json`, one file per class.
`scripts/failure-class` is their only schema authority; `scripts/test_failure_class.py`
covers it and runs in the `failure-class-cli-tests` manifest lane.

## Definition schema

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | Always `1`. |
| `id` | yes | `FC-<lower-kebab-slug>`; must match the filename. |
| `violated_contract` | yes | The contract an instance of this class breaks. |
| `canonical_prevention` | yes | Prose: the shape of the fix that removes the class. |
| `canonical_prevention_artifact` | no | Repository-relative paths to the **reusable guard surface** — a checker, shared fixture, or behavioral contract test. Every listed path must exist; a rename that orphans one fails validation. |
| `evidence_prs` | yes | Merged PRs that evidence the class. |
| `scope_hints` | no | Advisory globs; never used to classify a change. |
| `status` | yes | `open` or `dormant`. |
| `dormant_since` | dormant only | ISO-8601 timestamp of the dormant transition. |

`canonical_prevention` says what should stop recurrence; `canonical_prevention_artifact`
says where that guard actually lives. A class with prose but no artifact has an intention,
not a guard — which is what the ratchet below measures.

## Legacy narrative entries

These predate the JSON registry and are kept for their closure history.

| Class | Violated contract | Canonical fix primitive | Status | Closed by | Not covered |
| --- | --- | --- | --- | --- | --- |
| FC-1 | A malformed or legacy Firestore document must not bypass the reader's explicit fail-open or fail-closed policy. | `backend/database/read_boundary.py` | Open — the 14-day closure observation starts when #9827 merges. | — | — |
| FC-6 | A Firestore transaction fake must reject reads after the first write; a lenient fake can certify production code Firestore rejects. | `backend/tests/unit/fixtures/strict_firestore_transaction.py` | Closed | Shared strict fixture and strict-by-default convention. | Boundaries without incident evidence; fake styles that cannot be classified mechanically; queries, deletes, retry, and contention semantics. |
