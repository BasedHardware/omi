# migration/

Teardown of the old cloud. Not a product storage backend.

This workspace holds the four deletion clients that used to sit under
`drivers/` — Firestore, GCS, Pinecone, Typesense — the cleanup
participants that named their contracts, and the postgres adapters that
record their receipts. They can scrub the legacy `users` tree, account
objects, `memories-backend` vectors, and the `legacy_conversations` /
`canonical_memory_atoms` search collections. They cannot read those
stores, and they cannot serve a user.

They are here because David ruled the new stack self-contained: no leak
except Firebase auth (and the chat model provider). The migration logic
was already written; it was living inside the product it is supposed to
be separate from. Moving it is how it stays written once.

## What this must never do

- Serve. There is no route, scheduler, or composition root in
  `apps/service` that binds these participants.
- Read. Every client here is delete-only.
- Be imported by `apps/service` or `drivers/`. `lint:imports` fails
  that. `lint:closure` forbids `migration/` on the production
  entrypoints.

Live search is FTS5. Chat attachments are a sqlite BLOB. Semantic search
is an unconfigured stub. `drivers/firebase` (auth) and `drivers/model`
stay where they are; they are the sanctioned leaks.

## Layout

- `drivers/firestore` — deletes the legacy Firestore `users` tree
- `drivers/gcs` — deletes legacy account objects
- `drivers/pinecone` — `/vectors/delete` against `memories-backend`
- `drivers/typesense` — scan/delete of the two legacy collections
- `workers/` — the four participants, plus the composite seam that would
  bind independently fenced stores. No composition root wires that seam.
- `postgres/` — receipt repositories and the unbound postgres cleanup
  participant. The SQL tables stay in `drivers/postgres/migrations/`;
  only the teardown clients moved.
