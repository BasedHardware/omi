# Siri and App Intents contract

This is the shared contract for the macOS and iOS implementations. Both clients use backend IDs as entity IDs. Local-only rows without a backend ID are not indexed. Siri behavior is English-first. The iOS deployment floor remains 15.0 and the macOS floor remains 14.0. Classic Remember and Start/Stop listening shortcuts work on iOS 16+ and macOS 14+. Personal Spotlight entity indexing and schema intents require iOS 27+ or macOS 27+; older systems retain the custom shortcuts without those entities.

**Build boundary (David's 2026-09-27 runner ruling):** required GitHub desktop Swift and iOS compile checks use the standard `macos-26` image and Xcode 26.6 (Swift 6.3). `#if compiler(>=6.4)` excludes the Xcode 27 Siri integration and its 27-only tests there; store hooks and the iOS Pigeon bridge are no-ops in that CI artifact. The advisory desktop `xcode-27` job compiles Siri tests and extracts metadata without blocking required team CI. Codemagic desktop and iOS releases use Xcode 27.0 (Swift 6.4), compile the full integration and include `Metadata.appintents`. The release packager rejects Xcode 26.6 rather than producing a Siri-less candidate. Runtime OS availability still controls which shipped Siri features appear on older macOS/iOS versions.

## Entities and index

| Entity | Apple schema | ID | Indexed content | Link |
| --- | --- | --- | --- | --- |
| `ConversationEntity` | `.notes.note` | conversation backend ID | title as `name`, overview/summary as `content`, start and update/finish dates; no transcript | `omi://conversation/<id>` |
| `MemoryEntity` | custom `IndexedEntity` | memory backend ID | first 60 characters as name, full active memory as content, creation date | `omi://memory/<id>` |
| `TaskEntity` | `.reminders.reminder` | action item backend ID | description, due date, completion state and dates | `omi://task/<id>` |
| `OmiFolderEntity` | `.notes.folder` | `conversations` or `memories` | Conversations or Memories | corresponding collection |
| `OmiListEntity` | `.reminders.list` | `omi` | Omi | task collection |

The Xcode 27 metadata processor rejects two entity types conforming to `.notes.note`; the memory type must stay custom. Although `IndexedEntity` and `indexAppEntities` exist on iOS 18, the note, reminder, folder and list schema entities and `IndexedEntityQuery` reindex API used here require iOS 27. Supporting iOS 18–26 indexing would require separate entity types and queries for the same private objects, with a second mapping and reindex path. This PR keeps one owner, eligibility and wipe path and limits indexing to iOS 27+/macOS 27+. The index includes completed, retained conversations from the last 180 days (newest 2,000), active unexpired memories (newest 5,000), all open tasks and tasks completed in the last 30 days. An account gets its own named Core Spotlight index. On sign-out or UID change, wipe before indexing another account. The setting **Use Omi with Siri & Apple Intelligence** defaults ON; OFF wipes the index and suppresses future indexing and donations, while explicit intents still work.

On iOS, engine-free Siri authorization exactly follows FirebaseAuth's persisted sign-in state. Every native intent, entity query, reindex and snapshot read requires a hydrated `Auth.auth().currentUser` whose UID matches the Siri snapshot owner. The mirrored ID token can supply credentials only after that match when Firebase token refresh fails; it never establishes account ownership. FirebaseAuth's `currentUser` getter waits for its queued saved-user hydration. If protected data is unavailable and hydration cannot finish, Siri refuses temporarily without wiping the account. A definitive signed-out or different-UID state fences Siri and schedules the named-index wipe. Thus a process death before the asynchronous Auth listener runs cannot leave Siri authorized for an account Firebase considers signed out; if Firebase did not persist sign-out, the app itself also remains signed in on restart.

The `.notes.createNote` intent must return a `.notes.note` entity for a newly saved memory. Because conversations already own that schema type and the metadata processor rejects a second one, the returned note is `ConversationEntity(id: memory backend ID, folder: Memories)`; Spotlight also represents the same memory as custom `MemoryEntity` for memory search. System reindexing can recreate the note even when the app did not explicitly index it. This is the sole dual-representation exception to one entity type per object. Every explicit memory removal or transition out of eligibility deletes **both** representations through the platform's centralized ID-to-representations deletion function; a full named-index wipe removes both as well. Eligible memory edits refresh both representations. A conversation uses only `ConversationEntity` in the Conversations folder.

### Index eligibility (one shared decision table)

Each row below is an AND condition. A missing required ID, owner, or completion date fails closed. `now` is evaluated at every incremental change, full rebuild, entity query/reindex, and launch maintenance. A live index timer removes rows as they cross a time cutoff. Collection folders and the Omi list have no private content and are present only while indexing is enabled for the current owner.

| Field / state | Conversation | Memory | Task |
| --- | --- | --- | --- |
| Backend ID and account owner | Nonempty server ID, synced into the current account's cache | Nonempty server ID; `uid` (when supplied) equals the current account; current account cache | Nonempty server ID, current account cache |
| Deleted / discarded | Neither deleted nor discarded | Not deleted | Not deleted |
| Archived tier | N/A | Missing/null `memory_tier` is legacy active `long_term`; `short_term` and `long_term` are active; explicit `archive` excluded. The backend rejects unknown enum values; the tolerant client decoder excludes only that row from Siri without failing the whole page | N/A |
| Expired / invalidated | N/A | `expires_at` and `invalid_at` absent or later than `now` | N/A |
| User rejected / dismissed | N/A | `user_review != false`, not dismissed | N/A |
| Visibility | Owner-visible `private`, `shared`, or `public`; no hidden/unknown value | Owner-visible `private`, `shared`, or `public`; no hidden/unknown value | No visibility field in task response |
| Lifecycle status | Completed only; in-progress, processing, merging, failed excluded | Ledger status absent or active, no `superseded_by` | Active open, or completed within 30 days; cancelled, superseded and `superseded_by` excluded |
| Locked / paywalled | `is_locked == false` | `is_locked == false` | `is_locked == false` |
| Age window | Started (or created) later than `now - 180 days` | No creation-age limit | Open tasks have no age limit; completed_at later than `now - 30 days` |

Source fields were checked against Dart `Memory`, `ServerConversation`, `GeneratedActionItemResponse`; macOS GRDB `MemoryRecord`, `TranscriptionSessionRecord`, `ActionItemRecord`; and backend `MemoryDB`, `Conversation`, `ActionItemResponse`. Beyond the reported fields, this table explicitly covers locked/paywalled rows, memory invalidation and supersession, task supersession, and unknown visibility. The backend account-scoped fetch and local owner fence establish ownership where a row has no UID.

### Absent-value compatibility

The backend models are the authority for old documents that omit newer fields. Do not require a field to be explicitly present when its backend default is an indexable state. Explicit out-of-scope values remain excluded. The macOS cache may carry `nil` in columns added after the original row was stored; apply the same default there. This table covers every eligibility input above and the auxiliary fields that were audited.

| Field | Backend absence/default behavior (and null where applicable) | Siri decision on iOS and macOS |
| --- | --- | --- |
| Backend ID | Required by each response model; no default | Reject a missing or empty ID; local-only rows never enter the index. |
| Account owner | Memory `uid` is required. Conversation and task responses are fetched by the signed-in account and carry no UID. | Reject a missing or mismatched memory UID; fence the account-scoped cache and index by current owner on both platforms. |
| Sync provenance | No backend field; local cache state | Require an authoritative backend ID and current-account sync; no assumption from absent provenance. |
| Deleted / discarded | Memory and task deletion is represented by removal or a local tombstone; conversation `discarded` defaults false. | Keep a present, non-tombstoned row; absent `discarded` is false. |
| Memory `memory_tier` | `None`; backend reads existing documents as active, and the clients project them as `long_term`. | Include absent/null, `short_term`, and `long_term`; exclude explicit `archive`. Backend enum validation rejects an unknown `memory_tier`; if a malformed row reaches a released client, exclude only that row from Siri without throwing during whole-page decode. Unknown extra `layer`/`tier` aliases do not establish a tier; conflicting recognized aliases are Siri-ineligible without failing app decode. |
| Memory compatibility `expires_at` / `invalid_at` | `MemoryDB` has no `expires_at` field; the optional compatibility field is absent on normal responses. `invalid_at=None` means active. | Include until the earlier present deadline passes; missing deadlines do not exclude. Preserve `expires_at` through the Dart adapter and send that earliest deadline to the native snapshot timer. |
| Memory `user_review` / `is_dismissed` | `None` / false | Include unless explicitly rejected (`false`) or dismissed (`true`). |
| Memory visibility | `MemoryDB.visibility` defaults `public`; explicit null is allowed. | Include absent/null as owner-visible; exclude a present hidden or unknown value. iOS projects absent as public, macOS as private; both are owner-visible. |
| Conversation visibility | `Conversation.visibility` defaults `private`; explicit null is invalid in the backend, but older/malformed app payloads may contain it. | Include omitted/null as private in the app decoder so one row cannot reject a page; exclude explicit hidden or unknown string values. |
| Memory / conversation / task `is_locked` | false in all three backend response models | Include omitted/nil legacy lock flags as unlocked; exclude explicit true. |
| Memory `ledger_status` / `superseded_by` | `None` / `None` means current | Include absent status and empty supersession; exclude non-active status or a replacement ID. |
| Memory `kind` / `intent_backed` | `None` / false | Neither is a Siri eligibility prerequisite; old ordinary memories remain eligible. |
| Conversation `status` | Omission defaults to `completed`; explicit null is allowed by the optional backend field. | Both client adapters treat omitted/null as completed; exclude processing, in-progress, merging, and failed. |
| Task `status` / `superseded_by` | `active` / `None` in `ActionItemResponse` | Include omitted status as active; exclude cancelled, superseded, unknown explicit status, or a replacement ID. |
| Task `completed` / `completed_at` | `completed` is required; `completed_at=None` | Open tasks have no date requirement. A completed task without a completion date cannot prove the 30-day window and is excluded. |
| Conversation age | `started_at` is optional; `created_at` is required | Use `started_at`, falling back to `created_at`; include only within 180 days. |

iOS refreshes its private snapshot from an owner-wide, bounded traversal independent of the visible UI page: open tasks and recent completed tasks, completed conversations in the 180-day window, and the unfiltered memory view. It defers the refresh after account binding and schedules it no more than once per owner per launch day; confirmed mutations remain incremental. A complete traversal may reconcile absent IDs in its covered scope. A failed, rate-limited, truncated, partially decoded, or cap-limited traversal only adds fetched rows. The conversation 429 path honors `Retry-After` before one retry. macOS queries eligible conversations before applying its 2,000-row limit. Both clients use the earliest applicable memory expiry or ledger `invalid_at`, conversation age, and completed-task age to schedule removal while running.

On iOS, every owner transition, snapshot mutation, and Spotlight write, including system-requested `IndexedEntityQuery` reindex, enters one native serial queue in submission order. A single confirmed mutation upserts or deletes only its affected IDs; full delete-and-rebuild is reserved for authoritative reconciliation, launch maintenance, and toggle-on. Dart awaits each index call, including external sync callbacks. Undo or failed-delete restoration waits for the same ID's pending index deletion before re-upserting it. The same account fence applies inside the native queue, so a queued operation from an old owner cannot run under the next owner. macOS query callbacks and bounded sync batches pass IDs and the captured owner into the indexer; current storage rows are resolved after its owner-fenced operation gate is acquired, and missing IDs are removed. Sign-out and account-switch wipes wait for those operations to finish.

## Intents and phrases

| Action | Kind | Parameters | Result |
| --- | --- | --- | --- |
| Remember | `RememberIntent` and `.notes.createNote` in Memories | required text | `POST /v3/memories`, `category: manual`, `visibility: private`, `tags: [siri]`; confirm once, then say `Got it. I'll remember that <text>.` (short: `Saved to Omi`) |
| Open | `.system.open` | entity | navigate to the entity link in the foreground |
| Search | `.system.searchInApp` | criteria | foreground in-app search |
| Complete task | `.reminders.updateReminder` | task, `isCompleted` | only completion is supported; `PATCH /v1/action-items/<id>` and say `Marked '<title>' done.` |
| Create task | `.reminders.createReminder` | title, optional due date, Omi list | `POST /v1/action-items`; say `Added '<title>' to your Omi tasks.` |
| Start listening | custom intent | none | start the existing local capture path; say `Omi is listening.` |
| Stop listening | custom intent | none | stop that capture path; say `Omi stopped listening.` |

App Shortcut phrases: “Remember something in `\(.applicationName)`”; “Tell `\(.applicationName)` to remember”; “Add a memory to `\(.applicationName)`”; “Start listening with `\(.applicationName)`”; “Stop `\(.applicationName)`”. A missing Remember parameter prompts “What should Omi remember?”. Trim surrounding whitespace and an initial “that ”, then save the remaining text verbatim. Never report write success before the backend or authoritative local-first store confirms it. Remember, Complete and Create require local device authentication. Open and Search run in the foreground. iOS listening waits for the Flutter capture stack; macOS uses its existing capture controller. Ask Omi is outside this PR.

Failures have spoken, typed outcomes on both platforms: `auth` → “Open Omi and sign in first.”; `network` → “I couldn't reach Omi, so nothing was saved.” (or “the task wasn't changed”); `quota` (402) → “Your Omi limit has been reached, so nothing was saved.”; `rate_limited` (429) → “Omi is receiving too many requests. Try again shortly.”; `server` (5xx or malformed success) → “Omi couldn't save that right now.”; `cancelled` → no success claim. Unsupported task updates explain that Omi can only change completion through Siri. Do not turn a non-2xx response into an empty success.

Listening failures have their own dialogs: recording off → “Turn on audio recording in Omi first.”; microphone denied → “Allow microphone access in Omi first.”; stop with no phone capture → “Omi isn't listening right now.”; unavailable start/stop → “Omi couldn't start/stop listening right now” on macOS and “Open Omi to start/stop listening” on iOS when its foreground Flutter capture stack is unavailable. iOS has no macOS-style audio-recording-mode setting; its `recording_off` bridge code is retained for dialog parity if the capture controller introduces one.
Start on a paused phone stream or batch capture, or a macOS session paused while awaiting a meeting, says “Omi is paused. Open Omi to resume.” It never reports that listening started while no audio is flowing.

## Context, donations and telemetry

Annotate macOS conversation details, memory details, conversation rows and task rows with the corresponding App Entity ID. iOS uses `NSUserActivity.appEntityIdentifier` when a single conversation or memory detail is visible; Flutter canvas rows cannot be annotated individually. Attach entity IDs to relevant local notifications. Donate matching intents after UI memory creation, task completion or conversation opening, without including content in the donation.

Register `Siri Intent Performed` with `intent`, `platform`, `outcome`, `latency_ms`, `invoked_via`; values of `outcome` are `ok`, `auth`, `network`, `rate_limited`, `quota`, `server`, `cancelled`, and values of `invoked_via` are `siri`, `shortcuts`, `spotlight` where the system provides that source, or `unknown` otherwise. Register `Siri Index Rebuilt` with `platform`, `entity_counts`, `duration_ms`, `outcome`. Never send user content in analytics.

Pending David's rulings: R1 index scope, R2 default ON, R3 defer Ask Omi, R4 verbatim manual memory tagged `siri`.
