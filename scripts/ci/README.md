# Unfiltered main nightly

`main_nightly_full.yml` calls the PR test workflows with `nightly_main_sha`.
The source job resolves `main` once; branch dispatch validates the branch's
workflow definitions against that same main snapshot. Normal PR selection is
unchanged when the input is empty. Existing runner and timeout settings remain
in each called workflow (including GitHub's default when no cap is declared).

The graph covers backend unit shards, slow guardrails, emulators and hermetic
stacks; Flutter/Dart, Android and iOS; desktop Swift and Windows/Linux; all web
checks; SDKs, CLI, OpenAPI, source/image contracts and offline infrastructure
validation. `main.yml` is issue sync. Deploys, release automation, credentialed
private-image smoke, live evaluations and firmware are excluded.

No secrets are inherited. Existing issue-writer and private smoke jobs are
disabled by an explicit empty-input condition. Their caller permission ceilings
must still admit the dormant jobs' declarations; each running test job keeps
its existing read permissions. No issue, notification, cloud or repository
mutation runs in the nightly. Artifacts and the normal dependency caches stay
under GitHub Actions.

`nightly_main_report.py` reads completed job logs and writes `report.json`, a
job summary and `last-green-sha.txt`. The prior successful **main-branch** nightly
receipt owns the green SHA; the workflow run's head SHA can name a different
commit from the tested source. Before the first green nightly, the artifact
contains `none`. Missing previous receipts fail visibly rather than inventing
a bisect range. Setup failures without test records name the failed step.

The workspace lead reads the latest main run through
`infra/rollout/bin/nightly_main_read.sh`. It pins the run ID before downloading
the receipt, appends known-red rows, and posts one debt message per run attempt.
It performs no writes for pending, green or cancelled runs. A failed bus post
can be retried without duplicating rows.
