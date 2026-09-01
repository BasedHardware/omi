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
| `evidence_prs` | yes | Merged PRs that evidence the class. May be `[]` — a class added alongside its first fix has no merged PR to cite, and the adding commit is recoverable evidence. |
| `scope_hints` | no | Advisory globs; never used to classify a change. |
| `status` | yes | `open` or `dormant`. |
| `dormant_since` | dormant only | ISO-8601 timestamp of the dormant transition. |

`canonical_prevention` says what should stop recurrence; `canonical_prevention_artifact`
says where that guard actually lives. A class with prose but no artifact has an intention,
not a guard — which is what the ratchet below measures.

## Declaring a class

Write exactly one of these lines in the PR body. The value is a single token; the
alternatives below are alternatives, not a pipe-separated field:

```
Failure-Class: FC-<lower-kebab-slug>
Failure-Class: new
Failure-Class: none
```

`scripts/failure-class prepare` lists the classes whose advisory `scope_hints` overlap
the change's paths, which is a display narrowing and not a classification — the author
still chooses. `--all-candidates` lists the whole registry.

`Failure-Class: new` means this change adds exactly one definition file, alongside the
fix. It may not modify or remove any other definition; those transitions belong in a
registry-only PR. A new definition's `evidence_prs` may be empty, because the PR that
would be its evidence has no number until it is opened.

## Guard-artifact ratchet

`.github/scripts/check_failure_class_guard_ratchet.py` enforces the root `AGENTS.md` rule
that repeated fixes sharing one cause must produce a reusable guard surface, instead of
accumulating declarations forever. It runs in both manifest lanes as
`failure-class-guard-artifact-ratchet`.

- It counts **first-parent integration changes** whose message declares
  `Failure-Class: FC-<slug>`, over a 90-day window, plus the declaration in the PR body
  under review — so the PR that crosses the threshold is the one that fails. Raw commits
  are not counted: a single merged PR routinely carries many `fix:` commits.
- A class at or above **3** declarations in that window with no
  `canonical_prevention_artifact` fails the check.
- The check is history-dependent, so it degrades safely: on a shallow clone, or when the
  checked-out first-parent history does not reach back to the window start, it prints a
  loud `SKIP` and exits 0 rather than passing silently or failing spuriously.

To clear a failure, add the guard surface and record its path in the class definition.
Recording an artifact that does not exist fails `scripts/failure-class validate`.

### Grandfathered classes

`.github/scripts/failure_class_guard_ratchet_allowlist.json` records classes that were
already over threshold when the ratchet landed. Each entry's `declarations_at_baseline`
freezes the declaration count at ratchet introduction; a new declaration above that
baseline fails until the class records a guard artifact. The allowlist only shrinks: once a
class gains a `canonical_prevention_artifact`, the check fails until its allowlist entry is
removed. Adding an entry is an explicit, reviewable admission that a class is recurring
without a guard.

An instance-fix PR may add or update `canonical_prevention_artifact` on the declared class
in the same change; other definition edits still require a registry-only lifecycle PR.

## Legacy narrative entries

These predate the JSON registry and are kept for their closure history.

| Class | Violated contract | Canonical fix primitive | Status | Closed by | Not covered |
| --- | --- | --- | --- | --- | --- |
| FC-1 | A malformed or legacy Firestore document must not bypass the reader's explicit fail-open or fail-closed policy. | `backend/database/read_boundary.py` | Open — the 14-day closure observation starts when #9827 merges. | — | — |
| FC-6 | A Firestore transaction fake must reject reads after the first write; a lenient fake can certify production code Firestore rejects. | `backend/tests/unit/fixtures/strict_firestore_transaction.py` | Closed | Shared strict fixture and strict-by-default convention. | Boundaries without incident evidence; fake styles that cannot be classified mechanically; queries, deletes, retry, and contention semantics. |
