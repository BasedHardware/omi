# Tombstone restore-replay manifest and checkpoint contract

Status: pre-registered production-neutral P7 contract. This unit verifies
plain artifacts only; it does not restore, delete, replay, open traffic, or
contact a persistence system.

## Safety claim

A restored legacy or PostgreSQL generation is never traffic-eligible merely
because a replay loop ran. It becomes eligible only when one deterministic
checkpoint proves all of the following over the same exact coordinates:

1. a retention-locked terminal-export source issued a complete snapshot
   receipt at a declared monotonic high-water mark;
2. the supplied terminal-record manifest exactly matches that receipt in
   count, digest, source snapshot, and high-water mark;
3. the terminal source/deletion feed is held at that same high-water mark while
   the traffic decision is made;
4. the terminal set was captured no earlier than completion of the restored
   snapshot;
5. every manifest record has exactly one successful target outcome for that
   restore, and no unmanifested, duplicate, cross-account, or swapped outcome
   is present; and
6. the final checkpoint binds restore id, restored generation/snapshot and
   completion time, the exact retention-locked source receipt, terminal source
   snapshot/high-water mark, manifest, successful application set, and
   traffic-fence receipt.

The checkpoint means only that this lifecycle gate does not fence traffic. It
does not grant authentication, authorization, generation activation, account
epoch, entitlement, or application access.

## Artifacts

### Restore coordinate

The restore input names an opaque bounded restore id, one closed scope
(`legacy` or `postgresql`), the exact restored-snapshot digest, and the
restore-completion time. The verifier neither mints nor interprets the id.

### Terminal-set manifest and source receipt

Each manifest row contains only:

- opaque platform account id;
- terminal control revision;
- deletion epoch; and
- the immutable terminal-export record digest.

Rows are unique by account id and are canonically sorted by account id,
deletion epoch, control revision, and record digest before hashing. The
manifest binds its version, source snapshot digest, source high-water mark,
capture time, and exact row set.

The source receipt separately binds the same source snapshot/high-water mark,
manifest digest, exact row count, sink contract version, and a retention-locked
sink receipt digest. A zero-row manifest is valid only with a matching
zero-count source receipt; missing source state is never interpreted as an
empty terminal set.

### Traffic fence

The input carries a separately issued, held terminal-feed fence receipt bound
to the same source snapshot and high-water mark. A missing, released, older,
newer, or differently scoped fence blocks checkpoint production. The future
adapter must prove that the fence prevents a deletion after the source snapshot
from racing traffic admission; this pure unit validates coordinates, not the
external lock implementation.

### Target outcomes

An application outcome binds the restore id/scope, restored-snapshot digest,
account, terminal control/deletion coordinates, terminal-record digest, and a
closed result:

- `applied` or `already_absent`, each with one target receipt digest and no
  error code;
- `retryable_error` with one closed retryable code and no receipt; or
- `terminal_error` with one closed terminal code and no receipt.

Partial progress is explicit: outcomes may be a unique subset of the manifest.
Missing rows are pending, not success. Outcomes outside the manifest,
duplicates, owner/restore substitution, impossible receipt/error combinations,
or content-bearing reasons fail structurally.

## Verifier output

The frozen, deterministic report contains only versions, exact non-content
restore/source coordinates, digests, bounded counts, closed blockers, and an
optional checkpoint. It contains no account ids, manifest rows, transcript,
memory, product data, prompt, model output, provider/database error, SQL, path,
or free-form reason.

Blockers are closed and ordered:

- `terminal_set_predates_restore`;
- `terminal_feed_not_held`;
- `application_missing`;
- `application_retryable_error`; and
- `application_terminal_error`.

A checkpoint exists if and only if the blocker set is empty. Replaying the
same bytes produces the same checkpoint. Changing any restore, source,
manifest, application, or traffic-fence coordinate changes it. A consumer
must revalidate the held fence and current subordinate account control before
using the checkpoint; this artifact alone opens no route.

## Input boundary and cost

Inputs are exact detached plain data. Proxies, accessors, classes,
null-prototype records, sparse/decorated arrays, symbols, extras, non-finite or
unsafe integers, unbounded strings, duplicate accounts/outcomes, malformed
digests, and manifest/result sets above the fixed bound fail before hashing.
The verifier has no clock, environment, filesystem, database, network, model,
route, worker, or QA-store dependency. Runtime is linear in rows plus canonical
sort cost; no content enters the hash input.

## Deliberate exclusions and gates

- The retention-locked sink, terminal-feed fence, target deleters, restore
  runner, traffic gate, PostgreSQL role, Firebase/legacy adapter, and
  infrastructure are not implemented here.
- Source completeness is trusted only through the future authorized sink
  adapter's receipt. The core does not self-attest external durability.
- This is an account-tombstone replay proof. Item-level migration tombstones
  remain mandatory on every copy resume and are not summarized away.
- RPO/RTO, backup frequency, sink retention, legal hold, recovery authority,
  and data disposition remain David-gated.
- A real restore drill on both legacy and Cloud SQL, including a deletion race
  while the gate is held, remains a pre-cohort requirement.

## Pre-registered tests

1. Exact complete manifests for both restore scopes produce a checkpoint; the
   same bytes replay identically.
2. A zero-row manifest without an exact zero-count retention-locked source
   receipt fails; with one, it can pass.
3. Source receipt count/digest/snapshot/high-water mismatch fails before report
   creation.
4. A source capture predating restore completion blocks traffic.
5. Missing, released, or differently coordinated traffic fences block traffic.
6. Missing application rows remain pending; retryable and terminal errors stay
   distinct; none yields a checkpoint.
7. `applied` and `already_absent` are the only successful results and require
   a target receipt.
8. Extra, duplicate, swapped, cross-account, cross-restore, and mismatched
   terminal outcomes fail closed.
9. Manifest order and application completion order do not change the report or
   checkpoint.
10. Changing any identity-bearing coordinate changes the checkpoint digest.
11. Proxies, accessors, sparse/decorated arrays, extras, symbols, bad integers,
    overlong values, malformed digests, and over-budget sets are rejected
    without invoking hostile code.
12. Output is deeply frozen, omits account ids/rows, and is detached from later
    input mutation.
