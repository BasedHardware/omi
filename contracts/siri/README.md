# Siri and App Intents contract

This is the shared contract for the macOS and iOS implementations. Both clients use backend IDs as entity IDs. Local-only rows without a backend ID are not indexed. Siri behavior is English-first. The iOS deployment floor remains 15.0 and the macOS floor remains 14.0; APIs introduced later need availability gates and a usable older-system path.

## Entities and index

| Entity | Apple schema | ID | Indexed content | Link |
| --- | --- | --- | --- | --- |
| `ConversationEntity` | `.notes.note` | conversation backend ID | title as `name`, overview/summary as `content`, start and update/finish dates; no transcript | `omi://conversation/<id>` |
| `MemoryEntity` | custom `IndexedEntity` | memory backend ID | first 60 characters as name, full active memory as content, creation date | `omi://memory/<id>` |
| `TaskEntity` | `.reminders.reminder` | action item backend ID | description, due date, completion state and dates | `omi://task/<id>` |
| `OmiFolderEntity` | `.notes.folder` | `conversations` or `memories` | Conversations or Memories | corresponding collection |
| `OmiListEntity` | `.reminders.list` | `omi` | Omi | task collection |

The Xcode 27 metadata processor rejects two entity types conforming to `.notes.note`; the memory type must stay custom. The index includes completed, retained conversations from the last 180 days (newest 2,000), active unexpired memories (newest 5,000), all open tasks and tasks completed in the last 30 days. An account gets its own named Core Spotlight index. Delete indexed items in each local delete/expiry path. On sign-out or UID change, wipe before indexing another account. The setting **Use Omi with Siri & Apple Intelligence** defaults ON; OFF wipes the index and suppresses future indexing and donations, while explicit intents still work.

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

## Context, donations and telemetry

Annotate macOS conversation details, memory details, conversation rows and task rows with the corresponding App Entity ID. iOS uses `NSUserActivity.appEntityIdentifier` when a single conversation or memory detail is visible; Flutter canvas rows cannot be annotated individually. Attach entity IDs to relevant local notifications. Donate matching intents after UI memory creation, task completion or conversation opening, without including content in the donation.

Register `Siri Intent Performed` with `intent`, `platform`, `outcome`, `latency_ms`, `invoked_via`; values of `outcome` are `ok`, `auth`, `network`, `rate_limited`, `quota`, `server`, `cancelled`, and values of `invoked_via` are `siri`, `shortcuts`, `spotlight` where the system provides that source, or `unknown` otherwise. Register `Siri Index Rebuilt` with `platform`, `entity_counts`, `duration_ms`, `outcome`. Never send user content in analytics.

Pending David's rulings: R1 index scope, R2 default ON, R3 defer Ask Omi, R4 verbatim manual memory tagged `siri`.
