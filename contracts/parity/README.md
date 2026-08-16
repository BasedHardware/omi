# Cross-platform parity contracts

Omi ships the same product on Flutter (iOS/Android), macOS, and Windows, backed by one
Python backend. The recurring failure mode is a rule that gets fixed or changed on one
platform and silently diverges on another: local-day grouping was fixed for the app in
#10198 and again for macOS in #10980 and #10984, the Windows task bucketing comment
claims it mirrors the Flutter app while the app actually uses a different model (see
Divergence register below), and #11613 added a desktop route with no backend spec entry,
breaking an inventory guard for every open PR.

This directory holds the shared, platform-neutral fixture set for those rules. Each
platform runs the SAME vectors through its OWN production code in its own test suite.
A behavior change now requires editing a fixture here, which shows up in review as a
cross-platform decision instead of a single-platform drive-by.

## Fixture files

| File | Rule under contract |
|---|---|
| `task_due_buckets.json` | Task due-date bucketing (Today / Tomorrow / Later / No deadline, and the overdue handling models) |
| `day_keys.json` | Local-calendar-day identity of a UTC instant (conversation day grouping) |
| `wire_action_item.json` | Action item wire decode: due_at instant equality across ISO offset forms, and the null / missing / unparseable agreement set |
| `section_labels.json` | Relative day labels (Today / Yesterday / Tomorrow) as calendar-day relationships, including DST transition days |

## Conformance suites

| Platform | Suite | Runs |
|---|---|---|
| Backend (fixture integrity + serialization contract) | `backend/tests/unit/test_parity_contracts.py` | `backend/test.sh`, CI Backend unit suite |
| Flutter app | `app/test/parity/parity_contracts_test.dart` | `app/test.sh`, CI Flutter tests |
| Windows desktop | `desktop/windows/src/renderer/src/lib/parityContracts.test.ts` | `npm test` in `desktop/windows`, CI Desktop Windows tests |
| macOS desktop | Adapter pending. The fixtures already encode the macOS model (`fold_overdue`, `categoryFor` in `desktop/macos/Desktop/Sources/MainWindow/Pages/TasksPage.swift`); a `ParityContractsTests.swift` reading this directory is the follow-up for a machine that can run the Swift test lane. |

The backend suite validates every fixture file structurally (parseable, complete
expectations, self-consistent day-key arithmetic) so a malformed fixture cannot pass
vacuously on all clients at once, and pins the backend serialization side: due_at is
always emitted as an ISO-8601 instant with an explicit offset. Naive datetimes are the
one wire form the clients do NOT agree on (Dart and JS interpret them as local time,
Swift ISO8601 decoding rejects them), so the backend emitting them is the bug the
serialization contract exists to catch.

## Divergence register

Divergences that exist in production today. Each is encoded in the fixtures rather than
papered over; resolving one means changing the losing platform and updating the fixture
in the same PR.

1. Overdue model. The Flutter app (`app/lib/pages/action_items/task_categorization.dart`)
   uses a separate Overdue bucket: past-due tasks go to Overdue, and tasks with no due
   date created more than 7 days ago age into Overdue. macOS (`categoryFor`,
   `desktop/macos/Desktop/Sources/MainWindow/Pages/TasksPage.swift`) and Windows (`lib/taskBuckets.ts`) fold past-due into Today and have
   no aging rule. The Windows comment previously claimed the fold model matched the
   Flutter app; it does not, and `task_due_buckets.json` pins BOTH models per case so the
   difference is explicit until product picks one.
2. Missing created_at. The Windows sync mapper (`taskSyncEngine.ts` `mapBackendItem`)
   fills a missing created_at with the sync timestamp because its local store requires
   one; the Dart wire model keeps it null. Consumers must not treat the Windows value as
   a backend fact.
3. Completed view overdue. The Flutter overdue branches are skipped when viewing
   completed tasks (a completed past-due task shows under Today, a completed stale
   dateless task under No deadline). Bucket fixtures therefore model the open-tasks view.
4. Junk due_at strings (strict vs tolerant decode). A present-but-unparseable
   due_at ("", "not-a-date") makes the Dart generated wire reject the WHOLE item
   with a FormatException (its field reader treats a non-null field that reads to
   null as invalid), while the Windows sync mapper maps it to no-due-date and keeps
   the item. Found by this fixture set's first CI run: one corrupt timestamp in a
   list response breaks the app's decode path but not Windows sync. The backend
   sits on the strict side (it refuses to accept these forms, so it can never
   re-emit them); the `expected_by_model` cases in `wire_action_item.json` pin
   both client behaviors until the platforms converge.

## Adding or changing a case

1. Edit the fixture file here. Keep times as local calendar components (or UTC instants
   with per-offset expectations in `day_keys.json`); never bake one zone's epoch values
   into a shared expectation.
2. Run the backend integrity test, then each platform suite. Every adapter loads the
   fixture by relative path from the repo root, so there is nothing to regenerate.
3. If a platform legitimately disagrees, add a model column (as `task_due_buckets.json`
   does) and record it in the Divergence register with the owning files. Do not fork the
   fixture per platform.
