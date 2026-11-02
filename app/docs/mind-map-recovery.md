# Mobile Mind Map reads and recovery

The mobile Mind Map preserves a nonempty compatibility/shared graph. Empty or
owner-only results recover through `GET /v1/knowledge-graph/canonical`, a bounded,
revision-fenced projection of eligible, processed Long-term memories. Entity
nodes and relationships come only from server graph assertions. The separate
`catalog_nodes` response list represents saved memories even when their text cannot
support a relationship. Mobile displays those records as readable memories,
without synthesizing graph nodes or edges from their existence.
The read and renderer share the owner-node predicate, so duplicate owner labels
cannot hide saved memories and a single real entity remains visible.

Each page carries a signed cursor. Show More reads the next page and deduplicates
server IDs. The canvas retains the existing 200-entity overview bound, avoiding
unbounded quadratic simulation work as pages accumulate. Catalog records stay
separate and readable. Recovered maps fit the viewport on first display. A stale
cursor restarts the read from the current revision. Requests
are bound to an authenticated session and backend; page merges reject a different
session or backend. An expired cursor discards the invalidated revision before
restarting, including when that restart fails. A newer refresh supersedes earlier requests. Failed refreshes retain
same-session content and offer retry; a changed session or rejected authorization clears it.
Recovery follows only a successful empty or owner-only compatibility read. A
failed compatibility read does not trigger another expensive graph request;
each compatibility or canonical read keeps the zero-retry policy.

For older servers or accounts without available canonical state, the existing
compatibility graph remains readable. An unavailable canonical read plus an
empty compatibility response is a loading failure, not proof of an empty account.
The backend marks positively absent state with the additive
`X-Omi-Knowledge-Graph-State: unestablished` header, preserving the released 503
status and body. Only that signal (or an older server's 404) allows an empty
compatibility response to appear as a genuinely new account.
Refresh and pagination never call rebuild or delete and never change memories,
promotion receipts, assertions, or subscription state.

## Relationship to existing work

- #20744 handles the intentionally rejected canonical rebuild during onboarding.
  Its synthetic status is not proof that a map is populated.
- #12878 proposes macOS UI and account-wide shared-projection rebuilding. It
  does not implement mobile catalog presentation, pagination, or refresh races.
  A working shared graph remains visible through the compatibility read.
  The canonical catalog recovery does not require that PR. Deploy the additive absence
  header before releasing mobile so legacy-only empty accounts remain distinct
  from failed canonical reads.
- #20481 and #20463 remain the customer verification trackers. This change
  cannot establish whether a particular account has eligible memories or repair
  missing canonical assertions through a legacy rebuild.

## Implementation and verification checklist

- [x] Generate the existing canonical-response DTO from OpenAPI.
- [x] Read canonical entities, catalog records, and signed pagination.
- [x] Keep catalog records distinct from asserted relationships.
- [x] Provide refresh and Show More on the mobile screen.
- [x] Reject stale responses and mixed-session page merges.
- [x] Refresh from page one after a cursor expires.
- [x] Skip onboarding's legacy rebuild after a successful canonical read.
- [x] Distinguish positive absence from an unreadable canonical revision.
- [x] Add HTTP decode, failure, pagination, and mobile UI regression coverage.
- [ ] Verify on physical iOS and Android devices with affected accounts.
- [ ] Merge, deploy the backend header, and release mobile; verify the reported map after updating.

Account checks, when still needed, must examine eligibility, processing, and
assertion/extraction state privately. Do not request memory contents publicly
or claim an account has been repaired based on a successful client read alone.
