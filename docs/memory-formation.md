# Memory formation as wired (local service)

This is the local producer path that turns a user-asserted note or a finalized
listen conversation into a synthesized memory the app can render. The model of
what a memory *is* was already built; this document describes how that model is
now *run*.

David's ruling (Option A): user edits and custom entries go through
consolidation, fully trusted (never filtered out), still structured like
everything else. That is the behavior of this path. There is no trust-based
filter. `core/extract/quality.ts` remains a distributional detector for a
collapsed extractor and is not retuned here.

## Pipeline

```
HTTP POST /v1/stm-notes/ops          Listen socket finalize
        |                                      |
        v                                      v
sealUserAssertedStmNote              sealListenFormationFinalization
write_door: "http"                   outbox enqueue
source_trust stamped later           |
        |                            v
        |                    formation-outbox-consumer
        v                            |
stm-note-ingestion  <---- same ----> listen-formation-ingestion
        |                            |
        +-------- formation work ----+
                     |
                     v
            scripted formation model
            (DeterministicFakeModel seam;
             no network provider;
             relation token `notes`;
             excerpt kept as argument surface)
                     |
                     v
            ledger append (provisionals,
            evidence, events, mentions)
                     |
                     v
            local visible promotion
            (new canonical revisions with
            literal arguments)
                     |
                     v
            GET /v1/memories
            QA synthesizer text
```

Composition root: `apps/service/composition/memory-formation.ts`, constructed
from `apps/service/app-facing.ts` (the same factory `bin/dev-server.ts` uses).

Modes:

- `wired` (default) — accept, form, promote, so facts can render.
- `accept-only` — queue work and do not drain. Used as the red-proof.
- `formation-without-promotion` — form provisionals but skip local promotion
  (provisionals do not render).

The HTTP door drains inline after ingest. Listen finalization enqueues, then
kicks a serialized drain. Tests that close a listen socket should still
`await service.memoryFormation.drain(...)` before asserting the read surface.

## Where `source_trust` travels

- User notes: `apps/service/stm/stm-note-ingestion.ts` stamps
  `source_trust: "user_asserted"` on the ingested conversation (evidence and
  events). Capture kind is `user_asserted_stm_note`. Identity authority stays
  `null`.
- Listen: `apps/service/listen/formation-ingestion.ts` stamps
  `source_trust: "listen-finalized"`.
- The field is schema-required on every evidence and event record
  (`minLength: 1`, default `"unattested"`). Formation carries it through. Local
  promotion copies `evidence_refs` from the provisional; it does not rewrite
  trust and it does not drop a record because of trust.

## HTTP write door

`POST /v1/stm-notes/ops` in `apps/service/routes/stm-notes.ts`.

This is a dedicated path. Memories stays read-only: `POST /v1/memories/ops`
remains 422 `invalid_envelope`. The door is not added to `WRITABLE_DOMAINS`.

Accepted envelope (compact JSON, exact keys):

```json
{
  "write_id": "<64 lowercase hex>",
  "account_epoch": 7,
  "domain": "stm-notes",
  "op": {
    "op": "create",
    "record_id": "<token>",
    "content": {
      "text": "Atlas likes oat milk at Harborline Cafe",
      "client_write_ref": "client-ref-or-null"
    }
  }
}
```

Authorization, in order: bearer principal, canonical envelope parse, write
fence (`applyWriteFence` / account epoch), `write_id` registry, then
`sealUserAssertedStmNote` with `write_door: "http"`. A note is a ledger write.
The route does not mint an authorized ledger context; `composeLocalMemoryFormation`
issues `memories.work.accept` / `memories.work.execute` through
`apps/service/auth/local-application-authorization.ts`.

The note is never quality-gated and never dropped for trust. Empty or
control-character content fails seal and returns 422 `invalid_envelope`.

Idempotency: byte-identical `write_id` + fingerprint replays the stored
outcome; a reused `write_id` with a different fingerprint is `write_id_reuse`.

## How an agent runs the round trip

From this repo root, against the local service (not `https://api.omi.me`):

1. Activate the account epoch (observe ×3 + activate), same order as
   `apps/service/routes/tasks-ops.test.ts`.
2. `POST /v1/stm-notes/ops` with the envelope above.
3. `GET /v1/memories?limit=25` with the same bearer token.
4. Assert at the rendered layer: some `items[].text` contains the fact
   (the QA synthesizer phrases `{subject} {predicate} (observed {observed_at})`).
   Locally the scripted extractor copies the excerpt into the subject surface
   and uses relation token `notes`, so the rendered sentence is
   `{excerpt} notes (observed {observed_at}).` — the user's words, structured.

The listen direction: open `/v4/listen`, send audio, close 1000, wait until the
session is `completed`, `await service.memoryFormation.drain(...)`, then the
same `GET /v1/memories` assertion.

The suite that measures this is `apps/service/routes/stm-notes.round-trip.test.ts`.
Red-proof: boot with `memoryFormationMode: "accept-only"` and the rendered
assertion fails; restore `wired` and it passes.

## Local promotion (named divergence)

Formation's STM-to-LTM plan abstains without owner identity. Integrator notes
carry `identity_authority_context: null` by contract, so they land as
`provisional_abstained`. Application recall only renders canonical durable
claims (`applicationVisibleClosure`).

The local step `apps/service/composition/local-visible-promotion.ts` writes
**new** canonical revisions with **literal** arguments (the observed surface)
so the existing QA synthesizer can speak the fact. It does not append
formation's plan and then dream-promote the same `claim_revision_id`. It does
not inject fake owner identity.

## Named gaps

- Durable consolidation kinds other than this local visible promotion
  (derived-group-dream, identity-cluster, predicate-batch, promotion adapters)
  are composed and currently stub `dependency_unavailable`. `runNext` is idle
  unless those adapters are later filled.
- The MCP write door (`write_door: "mcp"` / `mcp_legacy`) is typed and unbuilt.
- Formation's graph plan still abstains locally; the fact-carrying path is
  extraction + STM-to-LTM append + local literal promotion.
- The scripted extractor uses one argument whose surface is the excerpt and
  relation token `notes`. That can emit `sole_argument_covers_evidence` as a
  diagnostic finding. Findings are not a drop. `core/extract/quality.ts` is
  not retuned.
- Listen drain is kicked from `finalize` but not awaited inside the socket
  handler. Callers that assert the read surface must await `drain`.
- `core/extract/quality.ts` findings are diagnostic. They must not become a
  drop rule for user content.
