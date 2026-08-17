# Restore pretraffic consistency evidence

Status: inert production-neutral P7 verifier. It has no database, source-feed,
infrastructure, authentication, route, traffic, or deployment composition.

## Narrow result

`evaluateRestorePretrafficReadiness` evaluates exact detached structural
evidence and returns either closed blockers or
`consistent_checkpoint_evidence`. The latter is ephemeral, non-authoritative
evidence only. It does not mean admitted, ready, activated, authorized, or
safe-to-serve. It carries no account, account epoch, credential, grant, token,
entitlement, or traffic capability.

A real consumer must still obtain authoritative current evidence, authenticate
and authorize the caller, and re-evaluate at its final effect fence. This pure
unit does not establish provenance or freshness merely because a plain object
has the expected shape.

## Required conjuncts

The verifier binds:

- the restore id/scope, restored generation and snapshot digests, and restore
  completion time, including the expected target-identity digest;
- a persisted complete replay checkpoint candidate bound to that generation,
  feed generation, and partition topology. Its exact repository-normalized
  candidate digest and stable timestamped persistence-receipt digest are
  recomputed before it can contribute evidence;
- a current generation attestation bound to the restore, snapshot, generation,
  target identity, and attestation receipt;
- a complete feed coverage observation for the same restore/checkpoint, source
  snapshot, feed generation, and topology, whose current, gap-free, and applied
  high-water marks are identical to each other and to the checkpoint's exact
  high-water mark. An ahead feed invalidates the old checkpoint rather than
  treating it as coverage for later terminal records;
- one coherent current account-control projection interpreted by the shared
  application-control decision; and
- a current latest-retained-fence observation for that exact account.

Missing candidate or feed coverage, unavailable attestation or retained-fence
observation, any coordinate mismatch, source lag/gap, current control denial,
or any retained terminal fence blocks. A higher retained deletion epoch cannot
be weakened by a lower restore; in this conservative unit every retained fence
blocks, regardless of which restore produced it.

The control projection and retained-fence observation describe one account.
An active account with no retained fence can be internally consistent even
when unrelated accounts appeared in the global replay manifest. That does not
make this an account authorization decision.

## Boundary and remaining gates

Inputs must be exact ordinary plain data. Proxies, accessors, classes, extras,
symbols, malformed digests, unsafe counters, cross-account fences, and invalid
nested control records fail before hashing. Output is frozen, deterministic,
bounded, content-free, and account-free. Every accepted control coordinate is
bound indirectly into the evidence digest, so a later control revision cannot
reuse earlier evidence bytes.

Before any runtime composition, separately authorized adapters must prove the
generation attestation, retained-fence source, and held/gap-free terminal-feed
coverage. David still owns source-feed watermark/ack authority, global versus
account-scoped lag policy, restored-generation attestation ownership, final
route/effect fencing, RPO/RTO, and traffic/cohort activation.
