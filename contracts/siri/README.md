# Siri and App Intents contract

This is the shared contract for the macOS and iOS implementations. Both clients use backend IDs as entity IDs. Local-only rows without a backend ID are not indexed. Siri behavior is English-first. The iOS deployment floor remains 15.0 and the macOS floor remains 14.0. Classic Remember and Start/Stop listening shortcuts work on iOS 16+ and macOS 14+. Personal Spotlight entity indexing and schema intents require iOS 27+ or macOS 27+; older systems retain the custom shortcuts without those entities.

## Entities and index

| Entity | Apple schema | ID | Indexed content | Link |
| --- | --- | --- | --- | --- |
| `ConversationEntity` | `.notes.note` | conversation backend ID | title as `name`, overview/summary as `content`, start and update/finish dates; no transcript | `omi://conversation/<id>` |
| `MemoryEntity` | custom `IndexedEntity` | memory backend ID | first 60 characters as name, full active memory as content, creation date | `omi://memory/<id>` |
| `TaskEntity` | `.reminders.reminder` | action item backend ID | description, due date, completion state and dates | `omi://task/<id>` |
| `OmiFolderEntity` | `.notes.folder` | `conversations` or `memories` | Conversations or Memories | corresponding collection |
| `OmiListEntity` | `.reminders.list` | `omi` | Omi | task collection |

The Xcode 27 metadata processor rejects two entity types conforming to `.notes.note`; the memory type must stay custom. Although `IndexedEntity` and `indexAppEntities` exist on iOS 18, the note, reminder, folder and list schema entities and `IndexedEntityQuery` reindex API used here require iOS 27. Supporting iOS 18–26 indexing would require separate entity types and queries for the same private objects, with a second mapping and reindex path. This PR keeps one owner, eligibility and wipe path and limits indexing to iOS 27+/macOS 27+. The index includes completed, retained conversations from the last 180 days (newest 2,000), active unexpired memories (newest 5,000), all open tasks and tasks completed in the last 30 days. An account gets its own named Core Spotlight index. Delete indexed items in each local delete/expiry path. On sign-out or UID change, wipe before indexing another account. The setting **Use Omi with Siri & Apple Intelligence** defaults ON; OFF wipes the index and suppresses future indexing and donations, while explicit intents still work.

### Index eligibility (one shared decision table)

Each row below is an AND condition. A missing required ID, owner, or completion date fails closed. `now` is evaluated at every incremental change, full rebuild, entity query/reindex, and launch maintenance. A live index timer removes rows as they cross a time cutoff. Collection folders and the Omi list have no private content and are present only while indexing is enabled for the current owner.

| Field / state | Conversation | Memory | Task |
| --- | --- | --- | --- |
| Backend ID and account owner | Nonempty server ID, synced into the current account's cache | Nonempty server ID; `uid` (when supplied) equals the current account; current account cache | Nonempty server ID, current account cache |
| Deleted / discarded | Neither deleted nor discarded | Not deleted | Not deleted |
| Archived tier | N/A | Explicit `short_term` or `long_term` only; archive or unknown tier excluded | N/A |
| Expired / invalidated | N/A | `expires_at` and `invalid_at` absent or later than `now` | N/A |
| User rejected / dismissed | N/A | `user_review != false`, not dismissed | N/A |
| Visibility | Owner-visible `private`, `shared`, or `public`; no hidden/unknown value | Owner-visible `private`, `shared`, or `public`; no hidden/unknown value | No visibility field in task response |
| Lifecycle status | Completed only; in-progress, processing, merging, failed excluded | Ledger status absent or active, no `superseded_by` | Active open, or completed within 30 days; cancelled, superseded and `superseded_by` excluded |
| Locked / paywalled | `is_locked == false` | `is_locked == false` | `is_locked == false` |
| Age window | Started (or created) later than `now - 180 days` | No creation-age limit | Open tasks have no age limit; completed_at later than `now - 30 days` |

Source fields were checked against Dart `Memory`, `ServerConversation`, `GeneratedActionItemResponse`; macOS GRDB `MemoryRecord`, `TranscriptionSessionRecord`, `ActionItemRecord`; and backend `MemoryDB`, `Conversation`, `ActionItemResponse`. Beyond the reported fields, this table explicitly covers locked/paywalled rows, memory invalidation and supersession, task supersession, and unknown visibility. The backend account-scoped fetch and local owner fence establish ownership where a row has no UID.

iOS refreshes its private snapshot from an owner-wide, bounded traversal independent of the visible UI page: open tasks and recent completed tasks, completed conversations in the 180-day window, and the unfiltered memory view. It defers the refresh after account binding and schedules it no more than once per owner per launch day; confirmed mutations remain incremental. A complete traversal may reconcile absent IDs in its covered scope. A failed, rate-limited, truncated, partially decoded, or cap-limited traversal only adds fetched rows. The conversation 429 path honors `Retry-After` before one retry. macOS queries eligible conversations before applying its 2,000-row limit. Both clients use the earliest applicable memory expiry or ledger `invalid_at`, conversation age, and completed-task age to schedule removal while running.

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

## Context, donations and telemetry

Annotate macOS conversation details, memory details, conversation rows and task rows with the corresponding App Entity ID. iOS uses `NSUserActivity.appEntityIdentifier` when a single conversation or memory detail is visible; Flutter canvas rows cannot be annotated individually. Attach entity IDs to relevant local notifications. Donate matching intents after UI memory creation, task completion or conversation opening, without including content in the donation.

Register `Siri Intent Performed` with `intent`, `platform`, `outcome`, `latency_ms`, `invoked_via`; values of `outcome` are `ok`, `auth`, `network`, `rate_limited`, `quota`, `server`, `cancelled`, and values of `invoked_via` are `siri`, `shortcuts`, `spotlight` where the system provides that source, or `unknown` otherwise. Register `Siri Index Rebuilt` with `platform`, `entity_counts`, `duration_ms`, `outcome`. Never send user content in analytics.

Pending David's rulings: R1 index scope, R2 default ON, R3 defer Ask Omi, R4 verbatim manual memory tagged `siri`.
