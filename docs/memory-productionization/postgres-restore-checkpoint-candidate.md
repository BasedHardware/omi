# Untrusted PostgreSQL restore checkpoint candidates

Status: inert P7 evidence persistence only. A candidate is untrusted evidence,
not a release, admission, activation, authority, or traffic decision.

## Narrow claim

`PostgresRestoreReplayCheckpointRepository` accepts one exact PostgreSQL
tombstone-replay checkpoint candidate. Before PostgreSQL I/O it validates and
detaches every coordinate, recomputes the core
`tombstone-replay-checkpoint-v1` digest from the exact checkpoint fields, and
computes a candidate digest that additionally binds:

- the restored-generation and restored-snapshot digests;
- source snapshot, source-feed generation, partition topology, high-water mark,
  and record count;
- the manifest and retention-locked terminal-source receipt binding;
- the complete successful application set; and
- the terminal-feed fence receipt.

Inside one serializable transaction the driver assumes the existing dedicated
`omi_platform_restore` role and invokes one fixed security-definer function.
The function appends one content-free candidate per restore. Exact replay
returns the original recorded timestamp with a replay classification and the
same persistence receipt digest; the digest deliberately excludes the
recorded/replayed classification. Changed
coordinates under the same restore id fail as a conflict. The table and
function expose no account content, SQL capability, application-role table
access, mutable release head, or deletion/control mutation.

The repository's named read operation runs in a serializable read-only
transaction. Missing is distinct from failure. A loaded row is accepted only
after the driver recomputes the core checkpoint digest, candidate digest, and
stable persistence receipt digest; it then returns the exact production-neutral
`PersistedRestoreCheckpointCandidate` shape consumed by pretraffic readiness.

The SQL-side caller-supplied candidate digest is defense in depth for exact
replay. It is not self-attested authority: the driver recomputes it, and the
persisted record remains an untrusted candidate even when both digests match.

## Exact nonclaims

- A candidate does not prove fresh source-feed coverage at traffic-decision
  time, complete account/application closure, current subordinate control, or
  that infrastructure restored the generation it names.
- A candidate neither clears `account_restored_terminal_fences` nor makes a
  fenced account active. Those fences remain monotone denial evidence.
- There is no release table/head, release mutation, application admission
  check, route, runtime composition, backup/PITR implementation, traffic
  switch, or production default in this unit.
- The repository does not choose or authenticate approvers. Two-person
  content-bearing restore approval and manual post-restore release are
  ratified, but their concrete operator authority and receipt verifier remain
  separate gates.
- A complete source that omits an account/application surface, a denial-of-
  service risk in a restore adapter, and a restore never registered by
  infrastructure remain activation blockers.

## Verification

Fake-driver tests cover exact named-operation order, deterministic binding,
replay classification, mutation detachment, hostile input, bounded record
count, and closed conflict/serialization failures. Static tests prove the
database-global table is classified as retained restore safety evidence, is
append-only, has no application/public access, and contains no release or
traffic state. Real PostgreSQL role, replay, rollback, and conflict behavior
remain required before this candidate repository is used by a restore drill.
