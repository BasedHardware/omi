import { expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { formationCandidateManifestDigest, parseFormationOutcomeEnvelope } from "../../../core/consolidate/formation-outcome";
import { prepareDerivation, sha256CanonicalRedacted, type AtomicGraphTransition } from "../../../core/ledger";
import {
  authoritativeAppendRequestDigest,
  defineAuthoritativeLedgerRepository,
} from "./authoritative-ledger-repository";

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "principal:alice",
  account_id: "account:alice",
  application_id: "app:desktop",
  credential_id: "credential:one",
  credential_generation: 4,
  capability: "memories.write",
  grant_id: "grant:one",
  grant_version: 9,
  account_epoch: 12,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "firebase-id-token",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: "a".repeat(64),
}, 150);

const transition = (): AtomicGraphTransition => ({
  placement: { offline_experiment: true, allocations: {}, results: [] },
  derivation: prepareDerivation({
    attempt_id: "attempt:one",
    commit_id: "commit:one",
    owner_account_id: "account:alice",
    parent_commit: null,
    idempotency_key: "append:one",
    input_revisions: [],
    output_revisions: [],
    versions: {
      strategy_version: "strategy:v1", model_version: "none", prompt_version: "none",
      policy_version: "policy:v1", code_version: "code:v1", schema_version: "schema:v1",
      tokenizer_version: "none", tool_version: "tool:v1",
    },
    success_kind: "successful_empty",
  }),
  revisions: [],
  adjacency: [],
  artifacts: [],
});

const formationOutcome = (overrides: Record<string, unknown> = {}) => ({
  contract_version: "memory-formation-outcome-v2",
  owner_account_id: "account:alice",
  work_id: "work:one",
  input_frontier: "frontier:one",
  response_digest: "c".repeat(64),
  candidate_count: 0,
  candidate_manifest_digest: formationCandidateManifestDigest(0),
  coordinates: {
    contract_version: "memory-formation-outcome-v2",
    strategy_version: "strategy:v1",
    model_version: "model:v1",
    prompt_version: "prompt:v1",
    policy_version: "policy:v1",
    code_version: "code:v1",
    schema_version: "schema:v1",
    tokenizer_version: "tokenizer:v1",
    tool_version: "tool:v1",
    speaker_strategy_version: "speaker:v1",
    boundary_strategy_version: "boundary:v1",
  },
  extraction_outcomes: [],
  placement_outcomes: [],
  ...overrides,
});

test("append request digest changes when the complete formation outcome changes", () => {
  const plan = transition();
  const base = parseFormationOutcomeEnvelope(formationOutcome());
  const changed = parseFormationOutcomeEnvelope(formationOutcome({ response_digest: "d".repeat(64) }));
  expect(authoritativeAppendRequestDigest(plan, { kind: "formation", outcome: base }))
    .not.toBe(authoritativeAppendRequestDigest(plan, { kind: "formation", outcome: changed }));
});

test("sealed repository receives only a minted context and an explicit non-formation transition", async () => {
  const calls: unknown[] = [];
  const repository = defineAuthoritativeLedgerRepository(async (authorized, request) => {
    calls.push([authorized, request]);
    return { kind: "committed", commit_id: request.transition.derivation.commit.commit_id, sequence: 1 };
  });
  const plan = transition();
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  await expect(repository.append(context(), {
    append_attempt: {
      idempotency_key: "append:one",
      expected_parent_commit: null,
      request_digest: authoritativeAppendRequestDigest(plan, origin),
    },
    origin,
    transition: plan,
  })).resolves.toEqual({ kind: "committed", commit_id: "commit:one", sequence: 1 });
  expect(calls).toHaveLength(1);
});

test("durable job graph origins are closed, honest, and request-identity-bearing", async () => {
  const seen: string[] = [];
  const repository = defineAuthoritativeLedgerRepository(async (_authorized, request) => {
    if (request.origin.kind === "non_formation") seen.push(request.origin.reason);
    return { kind: "committed", commit_id: request.transition.derivation.commit.commit_id, sequence: 1 };
  });
  const plan = transition();
  const reasons = ["promotion", "identity_consolidation", "predicate_alignment"] as const;
  const digests = new Set<string>();
  for (const reason of reasons) {
    const origin = { kind: "non_formation" as const, reason };
    const requestDigest = authoritativeAppendRequestDigest(plan, origin);
    digests.add(requestDigest);
    await repository.append(context(), {
      append_attempt: {
        idempotency_key: "append:one",
        expected_parent_commit: null,
        request_digest: requestDigest,
      },
      origin,
      transition: plan,
    });
  }
  expect(seen).toEqual([...reasons]);
  expect(digests.size).toBe(reasons.length);
});

test("repository rejects missing accounting, owner substitution, and a changed request digest before the adapter", async () => {
  let calls = 0;
  const repository = defineAuthoritativeLedgerRepository(async () => {
    calls += 1;
    return { kind: "serialization_retryable" };
  });
  const plan = transition();
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  const attempt = { idempotency_key: "append:one", expected_parent_commit: null, request_digest: authoritativeAppendRequestDigest(plan, origin) };
  await expect(repository.append(context(), { append_attempt: attempt, transition: plan } as never)).rejects.toThrow("request has an invalid shape");
  await expect(repository.append(context(), { append_attempt: { ...attempt, request_digest: "b".repeat(64) }, origin, transition: plan })).rejects.toThrow("digest does not match");
  const foreign = transition();
  foreign.derivation = prepareDerivation({ ...foreign.derivation.commit, owner_account_id: "account:bob", attempt_id: "attempt:two", commit_id: "commit:two", idempotency_key: "append:two", input_revisions: [], output_revisions: [], versions: foreign.derivation.commit.versions, success_kind: "successful_empty" });
  await expect(repository.append(context(), { append_attempt: { idempotency_key: "append:two", expected_parent_commit: null, request_digest: authoritativeAppendRequestDigest(foreign, origin) }, origin, transition: foreign })).rejects.toThrow("owner outside");
  expect(calls).toBe(0);
});

test("repository rejects sparse, decorated, and accessor-bearing transition arrays before the adapter", async () => {
  let calls = 0;
  const repository = defineAuthoritativeLedgerRepository(async () => {
    calls += 1;
    return { kind: "serialization_retryable" };
  });
  const requestFor = (plan: AtomicGraphTransition) => ({
    append_attempt: {
      idempotency_key: "append:one",
      expected_parent_commit: null,
      // Boundary validation must reject hostile containers before any digest
      // canonicalizer can inspect or execute their contents.
      request_digest: "0".repeat(64),
    },
    origin: { kind: "non_formation" as const, reason: "repair" as const },
    transition: plan,
  });

  const sparse = transition();
  sparse.revisions = new Array(1) as AtomicGraphTransition["revisions"];
  await expect(repository.append(context(), requestFor(sparse))).rejects.toThrow("dense and undecorated");

  const decorated = transition();
  Object.defineProperty(decorated.revisions, "metadata", { value: "hidden" });
  await expect(repository.append(context(), requestFor(decorated))).rejects.toThrow("dense and undecorated");

  const accessor = transition();
  Object.defineProperty(accessor.revisions, "0", {
    enumerable: true,
    configurable: true,
    get: () => { throw new Error("must not execute"); },
  });
  Object.defineProperty(accessor.revisions, "length", { value: 1 });
  await expect(repository.append(context(), requestFor(accessor))).rejects.toThrow("own data elements");
  expect(calls).toBe(0);
});

test("repository requires exact durable derivation input and output manifests", async () => {
  const plan = transition();
  const origin = { kind: "non_formation" as const, reason: "repair" as const };
  const requestFor = (candidate: AtomicGraphTransition) => ({
    append_attempt: {
      idempotency_key: candidate.derivation.commit.idempotency_key,
      expected_parent_commit: candidate.derivation.commit.parent_commit,
      request_digest: "0".repeat(64),
    },
    origin,
    transition: candidate,
  });
  const implementation = defineAuthoritativeLedgerRepository(async () => ({
    kind: "committed", commit_id: "unreachable", sequence: 1,
  }));

  const changedInput = structuredClone(plan);
  (changedInput.derivation.attempt.input_revisions as unknown as unknown[]).push({
    revision_id: "injected", content: {}, content_hash: sha256CanonicalRedacted({}),
  });
  await expect(implementation.append(context(), requestFor(changedInput)))
    .rejects.toThrow("manifests do not match");

  const changedCommit = structuredClone(plan);
  changedCommit.derivation.commit.input_digest = "f".repeat(64);
  await expect(implementation.append(context(), requestFor(changedCommit)))
    .rejects.toThrow("attempt and commit disagree");

  const graph = structuredClone(plan);
  graph.revisions = [{
    kind: "entity", revision_id: "entity:unmanifested:r1",
    entity: {
      entity_id: "entity:unmanifested", entity_revision_id: "entity:unmanifested:r1",
      owner_account_id: "account:alice", handle: "unmanifested", labels: [],
    },
  }];
  graph.derivation.attempt.output_revision_ids = [];
  graph.derivation.attempt.output_revisions = [];
  graph.derivation.commit.output_revision_ids = [];
  graph.derivation.commit.output_revisions = [];
  await expect(implementation.append(context(), {
    ...requestFor(graph),
    append_attempt: {
      ...requestFor(graph).append_attempt,
      request_digest: authoritativeAppendRequestDigest(graph, origin),
    },
  })).rejects.toThrow("absent or changed");
});

test("formation appends require outcome-to-transition accounting before an adapter runs", async () => {
  let calls = 0;
  const repository = defineAuthoritativeLedgerRepository(async () => {
    calls += 1;
    return { kind: "committed", commit_id: "commit:one", sequence: 1 };
  });
  const plan = transition();
  const validFormationOrigin = { kind: "formation" as const, outcome: parseFormationOutcomeEnvelope(formationOutcome()) };
  const appendAttempt = { idempotency_key: "append:one", expected_parent_commit: null, request_digest: authoritativeAppendRequestDigest(plan, validFormationOrigin) };
  await expect(repository.append(context(), {
    append_attempt: appendAttempt,
    origin: validFormationOrigin,
    transition: plan,
  })).resolves.toEqual({ kind: "committed", commit_id: "commit:one", sequence: 1 });
  await expect(repository.append(context(), {
    append_attempt: appendAttempt,
    origin: {
      kind: "formation",
      outcome: parseFormationOutcomeEnvelope(formationOutcome({
        candidate_count: 1,
        candidate_manifest_digest: formationCandidateManifestDigest(1),
        extraction_outcomes: [{ kind: "accepted", candidate_ref: "candidate:1", claim_revision_id: "claim:missing", evidence_ids: ["evidence:one"], repair_codes: [] }],
        placement_outcomes: [{ kind: "retryable_error", input_provisional_revision_id: "claim:missing", attempt: 1, max_attempts: 2, error_code: "model_timeout", next_eligible_at: null }],
      })),
    },
    transition: plan,
  })).rejects.toThrow("accepted provisional claim is absent");
  await expect(repository.append(context(), {
    append_attempt: appendAttempt,
    origin: { kind: "non_formation", reason: "unbounded-user-text" as never },
    transition: plan,
  })).rejects.toThrow("reason is unsupported");
  expect(calls).toBe(1);
});

test("formation accounting rejects provisional revisions not emitted by extraction", async () => {
  let calls = 0;
  const repository = defineAuthoritativeLedgerRepository(async () => {
    calls += 1;
    return { kind: "serialization_retryable" };
  });
  const plan = transition();
  const provisional = {
    claim_lineage_id: "lineage:extra",
    claim_revision_id: "claim:extra",
    owner_account_id: "account:alice",
    predicate: "exists",
    arguments: [{
      slot_id: "subject",
      role: "subject",
      surface: "Alice",
      span: { start: 0, end: 5 },
      value: { kind: "source_local_ref" as const, ref: "source-local:evidence:one" },
    }],
    observed_speaker_slot_id: null,
    polarity: "positive" as const,
    temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" as const },
    evidence_refs: ["evidence:one"],
    policy_labels: [],
    source_language: "en",
    scope: { locality: "source_local" as const, scope_ref: null },
    lifecycle: "provisional" as const,
    ambiguity_markers: [],
    context_packet: null,
  };
  plan.revisions = [{ kind: "claim", revision_id: "claim:extra", claim: provisional as never, placement_status: "provisional_abstained" }];
  plan.placement = {
    offline_experiment: true,
    allocations: {},
    results: [{ input_provisional_revision_id: "claim:extra", disposition: "reject", operation: null }],
  };
  plan.artifacts = [{
    artifact_id: "artifact:extra",
    kind: "abstention_set",
    provisional_revision_id: "claim:extra",
    canonical_claim_revision_id: null,
    margin: null,
    risk_markers: [],
    unit_boundary_decision: "abstain",
    scope_locality: null,
  }];
  const origin = { kind: "formation" as const, outcome: parseFormationOutcomeEnvelope(formationOutcome()) };
  await expect(repository.append(context(), {
    append_attempt: {
      idempotency_key: "append:one",
      expected_parent_commit: null,
      request_digest: authoritativeAppendRequestDigest(plan, origin),
    },
    origin,
    transition: plan,
  })).rejects.toThrow("provisional revisions do not exactly match");
  expect(calls).toBe(0);
});
