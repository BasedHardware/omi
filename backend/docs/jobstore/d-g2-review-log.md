# SCA-1959 review record

This is an incomplete dark implementation. Readiness is false. No merge,
activation, serving acceptance or savings follows from these source receipts.

## First FIX at 28f07cbcb44ac6a8e787ac4956d217faba01a5c5

Studio Luna returned FIX on SCA-1959, comment
`01a1d5ea-75c7-78ac-a976-892736a374b5`, and recorded further defects on parent
SCA-1697, comment `01a1d5ee-a83c-7929-8766-d0ce6e216a8a`. Both concern the same
head. They are the existing first FIX context, not two new review requests.

| Finding | Repair and real local regression |
|---|---|
| Raw SQL can reopen FS or remove registration | 0009 refuses reverse-open while certificates are absent, DELETE/TRUNCATE, namespace rename and forged bootstrap. `test_jobstore_sql_boundary.py` exercises direct SQL and verifies that legacy writes still refuse after each attempted removal. |
| Migration map confused with null | Explicit protobuf null is the only safe migration value. `test_migration_status_only_explicit_null_is_non_narrowing` checks actual Commit interception. |
| Generation/purge write bypasses closure | Classify the hashed privacy-authority document without hashing its key again. `test_generation_purge_writer_closes_actual_hashed_owner_before_commit`; Q10 remains covered by `test_legal_hold_token_rotation_does_not_close_pg_owner`. |
| Redirect target never enters A1 | Discovering a new target restarts A1 before another allowing walk. `test_redirect_target_is_snapshotted_before_retrying_allowing_walk`. |
| Refused admission poisons healthy claims | Persist a refusal hold and release its lease without discarding custody/paid-attempt tokens. `test_closed_and_expired_admissions_do_not_poison_other_owners_claims`. |
| Admission/claim lock inversion | Sorted owner locks precede namespace and row locks; recheck candidates under authority. `test_restore_admission_and_claim_do_not_invert_owner_namespace_locks` forces the disputed interleaving using real PostgreSQL lock observations. |
| Required production integration is incomplete | **Still blocking.** The source checkpoint inventory and cutover harness explicitly enumerate the missing adapters, purge/recovery, reverse certificates and complete crash matrix. Primitive tests cannot discharge this finding. |

The normal primary review verdict and final exact-head privacy/custody second
look have not been obtained for a complete source implementation. No second
review round is requested by this repair checkpoint. The two-round maximum
continues to apply; privacy/custody/data-loss defects remain blocking.
