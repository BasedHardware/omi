# Mobile Home feed

Status: implementation contract, 2026-11-15. Owner: ANX `card:mobile-home-card-feed`.

Home displays server-authored compact cards. Episodes and standalone conversations remain the owning records. Display fields are maintained alongside lifecycle writes; there is no new feed collection. Historical list reads do not compose summaries, decode transcripts or hydrate every member. Existing released-client APIs remain compatible.

## HTTP boundary

`GET /v1/home/feed?limit=50&cursor=<opaque>` is the unfiltered authenticated Home timeline. Limit is bounded (1..100). The server merges episodes and eligible standalone conversations in descending recorded-time order with a stable kind/ID tie-breaker. The cursor binds account, query and policy version and uses values, not a surviving anchor document. It preserves every unconsumed source frontier. Invalid cursors return an explicit client error. An empty partial page never claims exhaustion.

Response shape:

```json
{
  "items": [{
    "id": "episode:example",
    "kind": "episode",
    "detail_id": "example",
    "sort_at": "2026-11-15T00:00:00Z",
    "started_at": "2026-11-15T00:00:00Z",
    "finished_at": "2026-11-15T00:10:00Z",
    "title": "Example",
    "emoji": "",
    "preview": "",
    "status": "completed",
    "home_step": null,
    "starred": false,
    "is_locked": false,
    "has_tasks": false,
    "member_count": 2,
    "sources": [],
    "summary_available": true,
    "revision": "opaque-version"
  }],
  "next_cursor": null,
  "has_more": false,
  "truncated": false,
  "generation": "opaque-account-window-version"
}
```

`kind` is `episode` or `conversation`; `id` includes that namespace and `detail_id` is the owning object's ID. Dates/revision/status are server-authored. `sort_at` is a deterministic pagination key, using arrival only when recording evidence is absent. Nullable `started_at` remains unknown in that case; the client groups these cards under Unknown and does not display an invented time or duration. Finished time and home_step may be null. Title/preview have bounded lengths. `generation` is an opaque equality token for authoritative loaded-window reconciliation; it is not ordered and does not invalidate otherwise well-scoped continuation cursors. A generation change clears unvalidated cached text and reconciles the loaded window. No transcripts, full notes, member list, audio or full conversation objects appear here. Current lock/privacy policy applies; locked rows expose only the existing allowed preview. Search/folder/date/star/discarded views retain their exact existing query semantics during the Home migration.

Before an account's source coverage is established, GET returns HTTP 409 with `detail: "home_feed_preparation_required"`. This explicit state is distinct from an outage, denied access or empty history. `POST /v1/home/feed/prepare` accepts no body and returns `{ready, processed, has_more}` after one bounded, resumable preparation chunk. The mobile client may drive bounded low-priority preparation while displaying its existing compatible history. It switches to the compact feed only after readiness. No GET schedules migration or generation, and no agent directly backfills production account data.

## Mobile behavior

Use a dedicated card model/provider/cache. First cached/remote page paints immediately. One request per query; stale account/filter completions cannot publish. Near-bottom prefetch targets a bounded seven-day card buffer (record/byte/request caps), never waits for a whole week before first paint, and handles sparse and dense windows. Retry remains possible; partial responses are distinct from end of history. Preserve live/local capture overlays and prevent duplicates.

Hydrated conversation and episode reads omit the separate encrypted display payload and its display metadata. Source-version and member-proof metadata remain owned by the source fence; logical detail mutations cannot replay stale encrypted display fields. Mobile wire decoding is generated from the Home OpenAPI models.

Opening a card navigates immediately with its cached display fields, then hydrates the owning episode or conversation through existing detail APIs. Member cards and transcript/audio are deeper demand. Do not synthesize loaded-empty detail from omitted content. Keep existing deletion, selection, starring, lock/paywall and processing/recovery behavior truthful; use authoritative server membership for episode-wide operations.

## Lifecycle and migration

Compact encrypted display content is separate from heavy content on owning records, and cheap status/order/visibility/revision metadata is queryable. All relevant writes (create, finish, compose, edit, star, membership, discard, merge, delete and access changes) update or invalidate projections. Stale projections must not leak removed source text. Cosmetic rebuilds can retry asynchronously; security invalidation precedes acknowledgement. Legacy data uses bounded, explicit compatibility reads until safely migrated; missing projections never make existing history vanish. Record that compatibility cost separately from the steady-state path. No production account-data backfill is performed directly by an agent.

Preparation enumerates existing sources by document ID, preserving progress and source update-time preconditions. It stamps the canonical recorded-time order key rather than claiming that a bounded created-at window can globally order late imports. A coverage marker alone cannot fence an old writer process that creates a document without the new fields. Release admission therefore requires all relevant writer artifacts to carry the new writer schema before enabling preparation/rolling out the new mobile client. Record exact source inclusion for each serving writer and query-index readiness; API deployment alone does not satisfy this condition.

Preparation processes at most 50 source/receipt candidates and 40 member snapshots per request, with 400-read/write limits. Requested query limits reserve the read budget before streaming; consumed snapshots and requested upper bounds are metered separately. Its processed-JSON stopping target is 2 MiB, with a 3 MiB pre-read ceiling plus a final selected document; JSON expansion prevents treating that as a strict wire-byte bound. An 8 MiB actual protobuf guard protects the staged Commit. Normal episodes up to 512 members prepare across transactions and publish only after completion. Oversized legacy aggregates retain their member conversations as standalone cards rather than blocking all history. These are compatibility costs, distinct from steady-state feed reads.

Legacy episode titles and ledes are recovered from the existing encrypted content during explicit preparation only. Reuse requires exact composed/retained membership, currently visible and unlocked members, and original source revisions no newer than the compose. Preparation retains each unversioned source's original update time across its own metadata writes; later instrumented mutations revoke that legacy proof. Missing or stale proof keeps the safe member-derived display. GET never selects the legacy content blob.

The no-I/O write fence folds source-version and episode-epoch changes into a copy of the original source update, preserving source preconditions, transforms and caller result positions. A typical conversation mutation adds two Home writes (dirty receipt and shared owner control); an episode mutation adds one owner-control write. Pure transform-only conversation writes require one additional source patch. Existing privacy-token writes are separate. Proven additive live appends, progress-only metadata and preparation's own `home_*` writes add no Home invalidation writes. Multiple source mutations share one owner-control write per Commit.

`HOME_FEED_ENABLED` defaults on and controls serving/preparation only. For the initial mixed-writer deployment, Release explicitly closes this switch, rolls all relevant writer artifacts and verifies index readiness, then enables with its scoped go-ahead. The release packet names an activation owner and deadline; mobile keeps the compatible timeline meanwhile. Maintaining derived write fencing while serving is closed permits a safe re-enable. The writer/artifact inventory starts at `backend/runtime_images.json`, including separate desktop and worker lineages; standing operator scripts or jobs on old checkouts remain an explicit unknown until their owners pin or stop them.

Cache cards separately from detail, scoped to account and policy. Older pages need authoritative reconciliation or change/tombstone invalidation; a newest-page refresh cannot prove old cache validity. Unknown access/offline state must not revive deleted/locked content. New account and logout clear in-memory and persistent ownership.

## Validation and release

Test grouped/hidden and dense/sparse history, equal timestamps, deleted cursor anchors, late imports, ownership changes, partial results/retries, edit/delete races, access changes, account switches and detail hydration. Assert no generation from scroll/prefetch and no transcript/member hydration in the steady-state feed path. Measure source/member reads, bytes, first-card latency, visible cards and repeated requests. Maintain bounded recovery outside passive reads. Backend deploy and mobile distribution are separately verified; a merged PR is not a live release.

Aggregate counters `omi_home_feed_work_total` report source documents, cards and payload bytes; `omi_home_feed_requests_total` and `omi_home_feed_seconds` report request outcomes and latency. `omi_home_feed_preparation_documents_total` separates compatibility metadata/member reads, projection writes and bytes. Labels contain no account IDs or content. Ratios compare work per card and request across equivalent traffic; smaller field projections alone do not reduce Firestore document-read billing. One-time preparation and ongoing invalidation writes must be included before claiming net savings.


Under HOME_STEP_PROJECTION, uncomposed and live episodes keep their retained
recordings as compact standalone cards. READY notes are immediately readable;
the app folds only today's pending recording cards into one Processing row
under Listening. Composition replaces those recording cards with the compact
episode card. Preparation remains fenced: GET refuses every partial generation,
so no intermediate chunk can publish both representations. This uses existing
card fields and never adds member IDs or transcript/notes hydration to Home GET.
The preparation control and per-episode progress record the projection policy;
a policy change requires a fully prepared replacement before serving resumes.
Disabling HOME_STEP_PROJECTION restores grouped compact preparation. Pending
collection Delete uses only its displayed recording IDs; full finished episode
Delete still waits for authoritative opened detail membership.
