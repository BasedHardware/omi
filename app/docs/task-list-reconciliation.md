# Task list deletion and refresh ownership

`ActionItemsProvider` owns the Tasks list and Home due-window projection. The
backend task ID is the identity on both surfaces; matching descriptions may be
separate tasks and must not be merged or deleted by title.

## Deletion pipeline

1. A staged single delete hides the task on both surfaces while Undo is available.
   Undo restores the same ID without contacting the delete endpoint.
2. Direct, committed staged and bulk deletes suppress their IDs in Tasks and
   incoming list responses while the server mutation is outstanding. A list
   response omitting an ID is not a delete acknowledgement.
3. A successful mutation records the current list-read ordinal. Only a complete,
   unfiltered read started after that acknowledgement can confirm absence.
4. The suppression remains until every older Tasks, load-more and Home read has
   settled, so a late response cannot reinsert an ID after its suppression retires.
   Partial, filtered, truncated and failed reads cannot prove absence.
5. Failed or partially failed deletes restore each failed ID at most once. An
   already visible row keeps its current fields. Successful IDs stay hidden.
6. Clearing the account clears suppression and acknowledgement state; old work
   remains fenced by the provider's existing session generation.

Pagination still uses the released offset API. PR #20458 prevents overlapping
pages from appending the same ID twice. This follow-up covers deletion/read
ordering and rollback; it does not change backend task creation or remove existing
records with distinct IDs.

## Implementation and rollout checklist

- [x] Reproduce pending-delete refresh and bulk rollback failures on main.
- [x] Fence suppression retirement by server acknowledgement and older reads.
- [x] Use the existing ID-aware restore path for bulk rollback.
- [x] Verify single, staged, bulk, partial-failure, late-read and account-reset cases.
- [x] Keep the #20458 overlapping-page regression passing.
- [ ] Merge and release the follow-up mobile change.
- [ ] Confirm Scott's result on the released build; compare IDs privately if needed.

No account inspection or historical duplicate cleanup is implied by these checks.
Release and reporter verification remain tracked in
[#20456](https://github.com/BasedHardware/omi/issues/20456).
The linked follow-up PR records the focused tests, protected contracts, seeded
mobile journeys and preflight results for the published source revision.
