# Memory productionization selective-port manifest

Status: P0 integration contract, 2026-08-11

## Decision

The production memory system is built into the canonical `omi-platform` service. The
research branch is evidence and source material, not a branch to merge. We will port
measured mechanisms behind explicit, versioned ports while preserving the rewrite's
authorization, account-control, plain-data, read-integrity, and service-composition
boundaries.

This is deliberately a selective port:

- canonical source: `codex/track3-backend-integration` at
  `e4d85d7b254d0182003a71fd47e8514bada2045d`;
- research source: `research/r1-drop-observability` at
  `e9be93dc41c57bfb3c9511062f26855d9eee6f78`;
- common ancestor: `3913ffed791c4718de3acc8f33d053c6b4d8c002`;
- integration lane: `codex/memory-productionization-integration`;
- clean canonical baseline: `bun test` — 1,047 passed, 0 failed, 142 files;
- direct research production delta from the common ancestor: 30 files, 2,966
  insertions, 177 deletions;
- whole-branch merge: rejected. The two branches contain 159 canonical-only and 102
  research-only commits. A direct tip comparison misleadingly presents newer canonical
  account and read controls as deletions.

No benchmark corpus, blind answer key, human grade, credential, model response cache, or
private transcript may enter this repository.

## Ratified architecture that the port must preserve

1. The canonical service is the executable. There is no second memory service or
   research daemon in production (ADR-008).
2. PostgreSQL is the production authority for the append-only ledger and versioned
   projections. SQLite remains a QA/offline reference adapter (ADR-009).
3. A proposition is born one-to-one with claim lineage. Grouping is a rebuildable
   projection, not write-time authority (ADR-013).
4. Deletion dominance and tombstone replay apply through formation, projection, read,
   backup, and replay paths (ADR-014).
5. Bun must be qualified in the exact release image, with blue-green and
   expand/contract release behavior (ADR-011).
6. The existing application authorization and recall-integrity boundaries remain
   authoritative. Research retrieval code may supply candidates or observability, but
   may not bypass those boundaries.

## First vertical slice

The first slice is intentionally hermetic and non-user-visible. It proves that the
research kernel can be expressed through canonical ports before any model call,
PostgreSQL migration, route behavior, or background worker changes.

Input:

- one small synthetic capture session committed in the repository;
- frozen extraction, speaker-frame, and boundary decisions represented as plain JSON;
- no real person, benchmark question, model call, network access, or environment flag.

Path:

1. capture evidence;
2. materialize provisional claims and explicit drop/error dispositions;
3. apply a frozen placement decision without converting errors into abstentions;
4. materialize one canonical claim per lineage with evidence closure and policy labels;
5. build the authorized projection through the canonical application read boundary;
6. produce cited, content-safe output and a semantic comparison manifest.

The fixture declares these coordinates instead of selecting behavior implicitly:

| Coordinate | First-slice value | Runtime status |
| --- | --- | --- |
| kernel contract | `memory-productionization-v1` | integration fixture only |
| extraction strategy | `grounded-reference-v1` | frozen decision adapter |
| speaker strategy | `session-frame-reference-v1` | frozen decision adapter |
| boundary strategy | `unit-boundary-reference-v1` | frozen decision adapter |
| projection strategy | `proposition-per-lineage-v1` | ratified invariant |
| read strategy | `authorized-synthesized-v1` | canonical read boundary |

The comparison is semantic, not byte equality between divergent implementations. It
normalizes and compares:

- evidence ids and evidence closure;
- provisional lineage and canonical head allocation;
- extraction dispositions, placement dispositions, and error preservation;
- predicate identity names and argument roles;
- policy labels and scope locality;
- lifecycle/supersession/tombstone state;
- entity adjacency and projection heads;
- citation presence and recall completeness/absence qualification;
- every version coordinate used to produce the result.

Canonical-only security coordinates, opaque ids, keyed digests, and wire envelopes are
asserted by canonical tests and are not expected to equal the older research output.

## Commit disposition

### Port as production mechanisms

These changes encode correctness, cost control, or observable error semantics. They must
be re-expressed against canonical interfaces and tests rather than cherry-picked blindly.

| Research commits | Mechanism | Production disposition |
| --- | --- | --- |
| `34cc4ec93f`, `924ab2ef91` | bounded/name-ordered predicate alignment and per-batch error isolation | port through a bounded consolidation port |
| `2e4df82247`, `cc0da32b6b`, `924af4d915` | once-per-cycle costs, prompt-byte cache keys, overlap, and per-cluster settlement | port with explicit budgets and deterministic settlement records |
| `6d22e23696`, `195d2e5678`, `bad249820f` | named extraction/drop dispositions and conservation evidence | port as durable events/counters; detectors remain detectors, not guards |
| `7d6e2d1128`, `1b08f579a2`, `95b1bb123d` | promotion errors are neither abstention nor deletion | port as a typed retryable error state with replay tests |
| `fc4ec6b7a9` | predicate identity is its name, not window slot ordinals | port as a schema invariant |
| `c320a49960`, `88f243e1c2` | evidence-preserving validation/repair and bounded contextual targets | port behind a versioned extraction strategy |
| `ae66d33a4c` | whole-session speaker reconciliation | port behind a versioned formation strategy; shadow before authority |
| `a0f5015db7`, `08c09078c8` | read-stage localization and assertion citation provenance | adapt into content-safe telemetry and trace contracts |
| `ece0c94544` | timing/token/call instrumentation | adapt to injected telemetry; do not port environment-selected log files |

### Preserve only as versioned shadow candidates

These mechanisms remain available for paired evaluation, but do not become production
defaults without the named gate.

| Research commits | Reason | Gate |
| --- | --- | --- |
| `6798dea26c` | GLM v5 boundary is calibrated evidence, not a cross-model default | model-specific paired calibration |
| `c2f99f61d6` | subject-tier routing touches the bystander privacy boundary | David decision before any `subject:*` admission change |
| `4000ac7362` | compose voice is measured but its default is not ratified | David decision on `OMI_COMPOSE_VOICE` successor |
| `8c3aa4a097` | identity counterevidence mechanism did not meet the blind identity floor | paired shadow evidence on both DeepSeek and GLM |
| `b7dcad0386` | authority grounding was locally useful but its candidate failed blind outcome | paired shadow evidence; never identity authority by itself |

Environment flags from research are not the production control plane. Shadow candidates
are selected by persisted, typed, versioned rollout configuration with an audit record.

### Do not port into the production path

- DeepSeek future-query, session-batch, bounded-deferral, typed-witness, and contrastive
  boundary probes (`ddddfb58ab`, `367a69c461`, `b51c2d06ec`, `85269086fd`,
  `b635e4b3f8`, `1b071b22b7`, `76eaceaf23`, `6df17661dd`) are retired or
  experimental prompt variants.
- The DeepSeek consolidation-judge probe (`b8b87c7d95`) remains research evidence until
  reliability is demonstrated.
- Entity dossier seed/focus probes (`5cfb84e8c0`, `9b11a0a2e2`, `f4dc974912`) do not
  become write or read authority. Entity dossiers will be built from the authorized graph
  after binding is production-safe.
- Mixed-voice, compose-subject, and arrival-reconsideration probes (`7f1e06e6ca`,
  `9de41b129d`, `34f18b173e`) remain offline experiments.
- Research harnesses, graders, labelers, corpus adapters, and store copies remain outside
  the production repository and runtime.

## File disposition for the direct research delta

| Research file | Disposition in canonical backend |
| --- | --- |
| `core/consolidate/identity.ts` | selectively port bounded batching and per-cluster settlement behind consolidation ports |
| `core/consolidate/identity.test.ts` | translate invariant tests; do not copy research-only fixtures |
| `core/consolidate/relations.ts` | selectively port name-ordered predicate batching and error isolation |
| `core/consolidate/relations.test.ts` | translate deterministic batching/identity tests |
| `core/extract/grounded.ts` | port typed dispositions, evidence-safe repair, and bounded target context behind a versioned strategy |
| `core/ledger/index.ts` | port typed retryable promotion failure without weakening canonical ledger/account controls |
| `core/retrieve/agentic.ts` | port only stage telemetry and citation provenance; keep prompt candidates outside application authority |
| `core/retrieve/agentic.test.ts` | translate provenance and stage-failure tests; exclude dossier/prompt outcome assertions |
| `core/retrieve/dogfood.ts` | do not port research compose-subject behavior |
| `core/retrieve/index.ts` | manually reconcile the once-per-cycle optimization with newer canonical read/security work; this is the only independently changed file on both branches |
| `core/retrieve/trajectory.ts` | port explicit full/structural analysis mode; profile canonical copied stores before changing the full default |
| `core/retrieve/trajectory.test.ts` | translate the single-snapshot-per-cycle invariant |
| `core/schema/index.ts` | port predicate identity-name invariant with domain-pending markers |
| `drivers/model/consolidation-judge-edge.ts` | offline research only; no production port yet |
| `drivers/model/consolidation-judge-edge.test.ts` | offline research only |
| `drivers/model/glm.ts` | do not port wholesale; split model-neutral ports from versioned GLM/DeepSeek adapters and injected telemetry |
| `drivers/model/glm.test.ts` | mine contract cases; exclude retired prompts and environment-switch tests |
| `drivers/model/grounded-extraction.test.ts` | translate typed disposition and evidence-safe repair cases |
| `drivers/model/offline-reconsideration-edge.ts` | offline research only |
| `drivers/model/port.ts` | extend canonical model ports only for prompt-byte cache identity and explicit version coordinates |
| `drivers/model/session-boundary-edge.ts` | offline research only |
| `drivers/model/speaker-frame.ts` | port as a bounded, versioned shadow formation adapter |
| `drivers/model/timing.ts` | adapt into content-safe injected telemetry; no filesystem/env authority |
| `drivers/model/unit-boundary-edge.ts` | keep GLM v5 as reference; build separate calibrated model adapters, never one cross-model default |
| `drivers/model/verdict-cache.ts` | port exact-request/prompt-byte cache identity with account/version separation |
| `drivers/sqlite/dream.ts` | reference implementation only; port state-machine invariants to PostgreSQL worker/projections |
| `drivers/sqlite/dream.test.ts` | translate error, settlement, and replay cases against the production port contract |
| `drivers/sqlite/index.ts` | retain SQLite as QA/offline adapter only; timing hooks become injected telemetry |
| `drivers/sqlite/predicate.test.ts` | translate predicate identity test to shared contract suite |
| `drivers/sqlite/stm.ts` | reference adapter only; port conservation and cycle accounting through durable formation queues |

## Naming and product decisions still open

Until these are ratified, code keeps the legacy name and carries the exact marker:

- `DIV-DOMCORE-001` — memory;
- `DIV-DOMCORE-006` — STM;
- `DIV-DOMCORE-007` — entity;
- `DIV-DOMCORE-008` — claim/fact/memory atom;
- `DIV-DOMX-001` — ledger;
- `DIV-DOMX-005` — core;
- `DIV-DOMX-006` — grant.

The following are human gates, not implementation defaults:

- bystander privacy boundary or any change to `subject:*` admission;
- `OMI_COMPOSE_VOICE` successor default;
- blind labeling/grading sessions and their requested cost;
- first-cohort expansion beyond one account (`UNK-MEM-003`);
- production deploy, push, or protected-environment mutation.

`UNK-MEM-001` is already decided: this canonical platform is the target. Legacy
`memory_ingestion` is evidence/reference only. `FEAT-MEM-010` legacy L2 promotion remains
deferred. The staged rollout/control-plane shape in `FEAT-MEM-011` should be adopted,
with typed persisted strategy versions rather than research environment variables.

## P0 exit checklist

- [x] Canonical and research refs are pinned.
- [x] Dedicated integration branch/worktree exists from the canonical ref.
- [x] Clean canonical `bun test` baseline is recorded.
- [x] Wholesale merge is rejected and the true merge-base delta is inventoried.
- [x] All 30 production-relevant research files have a disposition.
- [x] Port, shadow, offline-only, and killed commit groups are explicit.
- [x] Ratified architecture and human gates are explicit.
- [x] The synthetic comparison fixture and semantic manifest schema are committed.
- [x] The fixture passes on the canonical baseline without model or network access.

P0 is closed. Runtime source changes may now begin as separately tested vertical slices.

## P1 adoption record — grounded formation, 2026-08-11

The first measured extraction port is selective even within the four named
research commits (`6d22e23696`, `195d2e5678`, `c320a49960`, and
`88f243e1c2`). It does not copy the research file wholesale.

Adopted into the production-neutral core:

- one stable `candidate:<raw ordinal>` for every accepted or dropped model
  candidate, so a repaired earlier candidate cannot rename later claims;
- closed drop reasons and content-free subreasons, with no raw surface or
  relation crossing the durable formation boundary;
- case/whitespace-only relocation that stores the evidence's verbatim slice and
  records every normalized ambiguous offset;
- conservative temporal default, missing-slot ordinal, and generic-role repair,
  each carried as a typed repair code and a visible ambiguity marker;
- optional bounded contextual evidence: all supplied active evidence is
  readable, while only an explicit non-empty target subset can ground output;
- strict exact-envelope/plain-data parsing, candidate bounds, active evidence,
  and unique evidence ids before the model edge;
- monotone preservation of non-`subject:*` evidence policy labels into the
  provisional claim;
- a total formation outcome contract (`memory-formation-outcome-v2`): every raw
  candidate has one extraction outcome and every accepted candidate has exactly
  one admitted, abstained, retryable, or dead placement outcome;
- a content-safe SHA-256 of the exact strict response envelope plus candidate
  manifest, so omissions and changed model responses are replay-visible;
- response- and version-scoped formation work ids, provisional/lineage ids,
  mention/antecedent ids, transition keys, attempts, commits, and canonical ids.
  Exact replay includes every placement input (frontier, entities, valid time,
  parent, and identity authority) and returns the prior commit before a model
  call; reusing a work id with changed input or versions fails loudly, while a
  new work namespace coexists in the same ledger.

Explicitly not adopted:

- `OMI_DROP_SURFACES` and every core environment selector;
- durable or console diagnostics containing model-produced relation/surface
  text;
- duplicate-slot renaming or clearing an invalid speaker-slot annotation. The
  current subject-tier compatibility path can reconstruct owner authority from
  first-person text, so those research repairs are not fail-closed and remain
  explicit drops;
- the unrelated name-only predicate identity change from `fc4ec6b7a9`;
- any model, prompt, route, storage, compose-voice, or `subject:*` default
  change. The target-context instruction exists only on the explicit opt-in
  call shape; the default prompt path is unchanged.

The canonical transition was also corrected to resolve identity from the
persisted mention coordinate, not by reloading the evidence-wide speaker
coordinate for every mention. This prevents a non-speaker or repaired mention
from fitting an unrelated owner authorization. A dedicated adversarial test
proves the claim remains unresolved and non-canonical even when the model asks
to bind it to the owner.

`role_generic` and `temporal_default` remain observable semantic uncertainty,
not evidence that placement is safe. Production job wiring must preserve their
repair codes and may shadow/defer them independently. Compose receives no new
owner-voice authority in this slice; its default remains a David gate.
