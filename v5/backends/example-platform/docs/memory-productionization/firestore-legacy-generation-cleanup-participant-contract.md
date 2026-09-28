# Legacy Firestore generation cleanup participant

Status: implemented, route-free, production-inactive.

This P7 participant owns the terminal-deletion inventory contribution named
`legacy_generation_data` for the complete account-owned legacy Firestore tree.
It does not make Firestore authoritative for the canonical backend,
does not claim post-cutover stranded destination state, and does not
authorize disposition of an active `rolled_back_stranded` account.

## Source registry

The registry fixes one semantic resource, `legacy_user_tree`, at
`users/{uid}`. The scanner does not use a hand-maintained collection allowlist:
it enumerates every descendant collection under the owner document while the
legacy writer fence is held. This matches the current legacy account-deletion
implementation and covers missing roots with surviving subcollections, nested
children, non-memory user records, and future account-owned collections without
turning an omitted collection into a false zero. Global collections outside
`users/{uid}` are not claimed by this surface. The retained PostgreSQL deletion
tombstone and content-free receipts remain the non-resurrection authority.

## Required production fence

The participant accepts only a held legacy-writer capability. That capability
must:

1. bind the platform account to an exact sorted set of legacy Firebase owner
   keys and the recomputed mapping digest;
2. prevent all writers to the entire account-owned `users/{uid}` tree for the
   callback;
3. recursively enumerate document descendants, including missing parents with
   surviving subcollections;
4. return document paths and update times only, never Firestore fields; and
5. await and drain every operation before releasing the fence.

The implementation never assumes `account_id == Firebase uid`.

## Inventory and disposal

The injected REST client reads the owner root with a valid non-reserved field
mask, then uses per-document collection-ID enumeration and path-scoped listing.
It accepts only empty/absent returned fields and uses `showMissing=true`, because
Firestore parent deletion does not cascade and can leave children behind an
absent parent.

The tree is capped at 100,000 visited document nodes/collections, 100 descendant
levels, and 32 MiB of cumulative path/revision coordinates. Pagination is
incrementally hashed instead of retained a second time. The
participant freezes the sorted `(document_path, update_time)` set before
deletion, deletes deepest descendants first with an exact update-time
precondition, records one content-free retained receipt for the whole user tree,
and relies on the complete cleanup coordinator's second scan for physical-zero
completion. Replay reloads the receipt but scans and deletes any resurrection
again.

No document path, update time, Firebase uid, field, content, or credential is
stored in PostgreSQL. Migration 40 stores only project/database, fixed semantic
role, collection ID, counts, and digests behind cleanup-role-only named
functions.

## Policy boundary

This participant can run only inside the outer terminal deletion/export/legal-
hold eligibility fence. David's separate active-rollback rule remains:
stranded new-generation data stays inaccessible for 30 days, after which a
separately authorized disposition decision is required. This terminal cleanup
port cannot be reused to bypass that decision.

## Activation blockers

Production remains inactive until qualification proves:

- exact GCP project/database and Firestore IAM;
- the Firebase identity-to-platform-account mapping and every relevant legacy
  writer are covered by one real source fence;
- recursive enumeration reaches the full live account tree, including orphan
  descendants and any global account-owned records that are not under it;
- bounded REST pagination, request bytes, deadlines, update-time conflicts,
  and retry behavior within the 15-minute renewable cleanup lease;
- a seeded account is inventoried and deleted with the real provider; and
- the active 30-day rollback recovery/export/disposition path is implemented
  independently of terminal account deletion.

No provider credential, route, scheduler, cohort, default, or deployment is
introduced by this slice.
