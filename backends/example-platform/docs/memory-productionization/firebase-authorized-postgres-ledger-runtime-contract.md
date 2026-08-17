# Route-free Firebase-authorized PostgreSQL ledger runtime contract

Status: implemented and real-PostgreSQL qualified, inert by construction.

The production-shaped request authorization seam is
`drivers/postgres/firebase-authorized-ledger-runtime.ts`. It binds a verified
Firebase ID token to one fixed application and the `memories.write`
capability, reads the exact credential/grant and account-control projections,
then submits the caller-provided append to the complete PostgreSQL authority
repository.

The runtime exposes only `append(token, now, request)`. Construction receives
an explicit PostgreSQL pool, Firebase project, deployed-or-emulator identity
mode, ID-token verification adapter, application id, and context lifetime. It
does not read environment variables, mint credentials, choose an account,
open a route, install a token source, or activate PostgreSQL as the service
default.

Token verification checks Firebase revocation. The authorization and control
sources can execute only their fixed queries, each inside a coherent
serializable transaction. Those preliminary reads do not authorize the
effect: the ledger append opens a later serializable transaction, sets the
sealed request coordinates, and locks and revalidates the exact account,
control, credential, grant, principal, epoch, lifecycle, and destination state
before receipt replay or any write. A change between preliminary
authorization and append therefore denies the effect.

PostgreSQL `bigint` coordinates are normalized from canonical decimal strings
with safe-integer bounds. Ambiguous strings, malformed rows, extra fields,
owner substitution, query failure, invalid Firebase claims, and unavailable
control state all fail closed without provider text entering the result.

## Qualification

The pinned PostgreSQL 18.4 real-adapter test proves:

1. a production-source Firebase verifier is called with revocation checking;
2. exact Firebase identity and application-credential bindings select one
   active `memories.write` grant and coherent account-control projection;
3. an authorized request commits graph sequence 6 and exact replay returns the
   same commit without another graph mutation;
4. a new grant revision is inserted and made current after both preliminary
   reads but before the ledger transaction; and
5. the ledger's locked revalidation returns `grant_inactive`, writes no denied
   commit, and leaves the graph head at sequence 6.

The same real suite runs its PostgreSQL/Postgres.js parity corpus under pinned
Bun 1.3.14 and Node 24.19.0. The local harness stops the managed runtime and
preserves the labelled synthetic volume after the run.

This contract does not ratify a public memory route, request wire, runtime
credential source, deployment topology, PostgreSQL service default, Listen
ingestion, subject-tier policy, bystander boundary, compose voice, product
projection materialization subject, or rollout cohort.
