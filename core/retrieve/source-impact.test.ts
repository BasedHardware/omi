import { describe, expect, test } from "bun:test";

import type { GraphSnapshot } from "./index";
import {
  buildAuthorizedProductProjectionSet,
  buildProductProjectionRevision,
  birthProductProposition,
  type AuthorizedProductProjectionSet,
} from "./product-projection";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import { sha256CanonicalContent } from "./content-digest";
import {
  SourceImpactError,
  enumerateAuthorizedSourceImpact,
  type SourceImpactCodecs,
  type SourceImpactErrorCode,
  type SourceImpactPageRequest,
} from "./source-impact";
import { snapshot as baseSnapshot } from "./tree.fixture";

const digest = (character: string): string => character.repeat(64);

const authorizationRequest = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner",
    credential_kind: "mcp_api_key",
    app_id: "app:source-impact",
    key_id: "key:source-impact",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: "owner",
    consumer: "mcp",
    app_id: "app:source-impact",
    key_id: "key:source-impact",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});

const rawSnapshot = (addHidden = false): GraphSnapshot => {
  const base = baseSnapshot();
  const visibleEvidence = {
    ...base.evidence![0]!,
    evidence: {
      ...base.evidence![0]!.evidence,
      evidence_id: "evidence:raw-visible-sentinel",
      source_unit_ref: "source-unit:raw-visible-sentinel",
    },
  };
  const visibleEvent = {
    ...base.events![0]!,
    revision_id: "event:raw-visible-sentinel",
    event: {
      ...base.events![0]!.event,
      event_id: "event:raw-visible-sentinel",
      event_revision_id: "event:raw-visible-sentinel",
      capture_session_id: "capture:raw-visible-sentinel",
      evidence_addressable_refs: [visibleEvidence.evidence.evidence_id],
    },
  };
  const claims = base.claims.map((entry) => entry.revision_id === "a" ? {
    ...entry,
    claim: {
      ...entry.claim,
      evidence_refs: [visibleEvidence.evidence.evidence_id],
    },
  } : entry);
  if (!addHidden) return {
    ...base,
    claims,
    evidence: [{ ...visibleEvidence, evidence: { ...visibleEvidence.evidence, event_revision_id: visibleEvent.event.event_revision_id } }],
    events: [visibleEvent],
  };
  const hiddenEvent = {
    revision_id: "event:hidden-sentinel",
    event: {
      ...visibleEvent.event,
      event_id: "event:hidden-sentinel",
      event_revision_id: "event:hidden-sentinel",
      capture_session_id: visibleEvent.event.capture_session_id,
      evidence_addressable_refs: ["evidence:hidden-sentinel"],
    },
  };
  const hiddenEvidence = {
    revision_id: "evidence:hidden-sentinel:r1",
    evidence: {
      ...visibleEvidence.evidence,
      evidence_id: "evidence:hidden-sentinel",
      event_revision_id: hiddenEvent.event.event_revision_id,
      source_unit_ref: visibleEvidence.evidence.source_unit_ref,
      excerpt: "raw hidden source text sentinel",
      state: "security_hidden" as const,
      policy_labels: ["sensitivity:private"],
    },
  };
  const hiddenClaim = claims.find((entry) => entry.revision_id === "private")!;
  return {
    ...base,
    claims: claims.map((entry) => entry.revision_id === "private" ? {
      ...hiddenClaim,
      claim: { ...hiddenClaim.claim, evidence_refs: [hiddenEvidence.evidence.evidence_id] },
    } : entry),
    evidence: [
      { ...visibleEvidence, evidence: { ...visibleEvidence.evidence, event_revision_id: visibleEvent.event.event_revision_id } },
      hiddenEvidence,
    ],
    events: [visibleEvent, hiddenEvent],
  };
};

const authorizedInput = (addHidden = false): ApplicationGrantProjectedTreeInputSnapshot =>
  readAfterApplicationAuthorization(authorizationRequest(), () => ({
    snapshot: rawSnapshot(addHidden),
    options: { account_timezone: "UTC" },
  }));

const projections = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  reverse = false,
): AuthorizedProductProjectionSet => {
  const claim = input.claims[0]!;
  const born = birthProductProposition({
    owner_account_id: input.owner_account_id,
    proposition_id: "proposition:raw-visible-sentinel",
    birth_claim_lineage_id: claim.claim_lineage_id,
    origin: "native",
    graph_frontier: input.graph_generation,
    input_digest: digest("a"),
    result_digest: digest("b"),
    created_at_event_time: 10,
  });
  const make = (sequence: number) => buildProductProjectionRevision({
    identity: born.identity,
    membership: born.membership,
    projection_sequence: sequence,
    graph_frontier: input.graph_generation,
    renderer_contract_digest: digest("c"),
    rendered_content_digest: sequence === 1 ? digest("d") : digest("e"),
    citations: [{
      claim_lineage_id: claim.claim_lineage_id,
      claim_revision_id: claim.claim_revision_id,
      evidence_refs: [...claim.evidence_refs].sort(),
    }],
    created_at_event_time: 20 + sequence,
  });
  const values = [make(1), make(2)];
  return buildAuthorizedProductProjectionSet(
    input,
    [born.identity],
    [born.membership],
    reverse ? values.reverse() : values,
  );
};

interface CodecHarness {
  readonly codecs: SourceImpactCodecs;
  readonly calls: { refs: number; verifies: number; issues: number };
}

const codecHarness = (): CodecHarness => {
  const cursors = new Map<string, { binding_digest: string; after_key: string }>();
  const calls = { refs: 0, verifies: 0, issues: 0 };
  return {
    calls,
    codecs: {
      encode_ref: (input) => {
        calls.refs += 1;
        return `si1_${sha256CanonicalContent(input)}`;
      },
      verify_cursor: ({ cursor, binding_digest }) => {
        calls.verifies += 1;
        const stored = cursors.get(cursor);
        return stored?.binding_digest === binding_digest ? stored.after_key : null;
      },
      issue_cursor: (input) => {
        calls.issues += 1;
        const cursor = `sic1_${sha256CanonicalContent(input)}`;
        cursors.set(cursor, { ...input });
        return cursor;
      },
    },
  };
};

const request = (overrides: Partial<SourceImpactPageRequest> = {}): SourceImpactPageRequest => ({
  target: { kind: "capture_session", capture_session_id: "capture:raw-visible-sentinel" },
  limit: 100,
  cursor: null,
  ...overrides,
});

const expectCode = (code: SourceImpactErrorCode, operation: () => unknown): void => {
  try {
    operation();
    throw new Error("expected source impact error");
  } catch (error) {
    expect(error).toBeInstanceOf(SourceImpactError);
    expect((error as SourceImpactError).code).toBe(code);
  }
};

describe("authorized source impact core", () => {
  test("returns only opaque deterministic dependencies with current projection state", () => {
    const input = authorizedInput();
    const product = projections(input);
    const harness = codecHarness();
    const beforeInput = JSON.stringify(input);
    const beforeProduct = JSON.stringify(product);

    const first = enumerateAuthorizedSourceImpact(input, product, request(), harness.codecs);
    const second = enumerateAuthorizedSourceImpact(input, product, request(), harness.codecs);

    expect(first).toEqual(second);
    expect(first.items.map((item) => item.kind)).toEqual([
      "event", "evidence", "canonical_claim", "product_projection", "product_projection",
    ]);
    expect(first.items.filter((item) => item.kind === "product_projection").map((item) => item.state).sort())
      .toEqual(["current", "historical"]);
    expect(first.items.every((item) => item.recomputability === "recomputable")).toBe(true);
    expect(first.has_more).toBe(false);
    expect(first.next_cursor).toBeNull();
    expect(first.query_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(first.snapshot_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify(input)).toBe(beforeInput);
    expect(JSON.stringify(product)).toBe(beforeProduct);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.items)).toBe(true);

    const serialized = JSON.stringify(first);
    for (const raw of [
      "owner", "capture:raw-visible-sentinel", "source-unit:raw-visible-sentinel",
      "event:raw-visible-sentinel", "evidence:raw-visible-sentinel", "proposition:raw-visible-sentinel",
      "excerpt", "policy_labels", "source_unit_ref", "capture_session_id",
    ]) expect(serialized).not.toContain(raw);
  });

  test("walks stable pages without gaps and binds cursors to the exact query", () => {
    const input = authorizedInput();
    const product = projections(input);
    const harness = codecHarness();
    const first = enumerateAuthorizedSourceImpact(input, product, request({ limit: 2 }), harness.codecs);
    expect(first.has_more).toBe(true);
    expect(first.next_cursor).toMatch(/^sic1_[a-f0-9]{64}$/);
    const second = enumerateAuthorizedSourceImpact(
      input, product, request({ limit: 2, cursor: first.next_cursor }), harness.codecs,
    );
    const third = enumerateAuthorizedSourceImpact(
      input, product, request({ limit: 2, cursor: second.next_cursor }), harness.codecs,
    );
    expect([...first.items, ...second.items, ...third.items]).toHaveLength(5);
    expect(new Set([...first.items, ...second.items, ...third.items].map((item) => item.ref)).size).toBe(5);
    expect(third.has_more).toBe(false);
    expect(third.next_cursor).toBeNull();

    expectCode("invalid_cursor", () => enumerateAuthorizedSourceImpact(
      input,
      product,
      request({
        limit: 2,
        cursor: first.next_cursor,
        target: { kind: "evidence", evidence_id: "evidence:raw-visible-sentinel" },
      }),
      harness.codecs,
    ));
  });

  test("evidence and capture targets agree for the same authorized span", () => {
    const input = authorizedInput();
    const product = projections(input);
    const capture = enumerateAuthorizedSourceImpact(input, product, request(), codecHarness().codecs);
    const evidence = enumerateAuthorizedSourceImpact(input, product, request({
      target: { kind: "evidence", evidence_id: "evidence:raw-visible-sentinel" },
    }), codecHarness().codecs);
    expect(evidence.items).toEqual(capture.items);
    expect(evidence.query_digest).not.toBe(capture.query_digest);
  });

  test("authorized input order and upstream hidden descendants cannot perturb output", () => {
    const clean = authorizedInput(false);
    const withHidden = authorizedInput(true);
    expect(withHidden).toEqual(clean);

    const forward = enumerateAuthorizedSourceImpact(clean, projections(clean, false), request(), codecHarness().codecs);
    const reversed = enumerateAuthorizedSourceImpact(clean, projections(clean, true), request(), codecHarness().codecs);
    const hidden = enumerateAuthorizedSourceImpact(withHidden, projections(withHidden), request(), codecHarness().codecs);
    expect(reversed).toEqual(forward);
    expect(hidden).toEqual(forward);
    expect(JSON.stringify(hidden)).not.toContain("hidden-sentinel");
    expect(JSON.stringify(hidden)).not.toContain("raw hidden source text sentinel");
  });

  test("unbranded and coordinate-mismatched inputs fail before codec access", () => {
    const input = authorizedInput();
    const product = projections(input);
    const otherAuthorization = authorizationRequest();
    const otherInput = readAfterApplicationAuthorization({
      ...otherAuthorization,
      credential: { ...otherAuthorization.credential, key_id: "key:other-source-impact" },
      persisted_grant: { ...otherAuthorization.persisted_grant!, key_id: "key:other-source-impact" },
    }, () => ({ snapshot: rawSnapshot(), options: { account_timezone: "UTC" } }));
    const otherProduct = projections(otherInput);
    const harness = codecHarness();
    expectCode("unauthorized_input", () => enumerateAuthorizedSourceImpact(
      { ...input } as ApplicationGrantProjectedTreeInputSnapshot,
      product,
      request(),
      harness.codecs,
    ));
    expectCode("unauthorized_input", () => enumerateAuthorizedSourceImpact(
      input,
      { ...product } as AuthorizedProductProjectionSet,
      request(),
      harness.codecs,
    ));
    expectCode("coordinate_mismatch", () => enumerateAuthorizedSourceImpact(
      input,
      otherProduct,
      request(),
      harness.codecs,
    ));
    expect(harness.calls).toEqual({ refs: 0, verifies: 0, issues: 0 });
  });

  test("malformed requests and hostile codecs fail closed", () => {
    const input = authorizedInput();
    const product = projections(input);
    const harness = codecHarness();
    for (const invalid of [
      { ...request(), limit: 0 },
      { ...request(), limit: 101 },
      { ...request(), extra: true },
      { ...request(), target: { kind: "evidence", evidence_id: "" } },
      { ...request(), cursor: "not-opaque" },
      Object.defineProperty({ ...request() }, "limit", { enumerable: true, get: () => 10 }),
      new Proxy(request(), {}),
    ]) expectCode(invalid && "cursor" in invalid && invalid.cursor === "not-opaque" ? "invalid_cursor" : "invalid_request", () =>
      enumerateAuthorizedSourceImpact(input, product, invalid as SourceImpactPageRequest, harness.codecs));

    expectCode("invalid_codecs", () => enumerateAuthorizedSourceImpact(
      input, product, request(), new Proxy(harness.codecs, {}),
    ));
    expectCode("invalid_codecs", () => enumerateAuthorizedSourceImpact(
      input, product, request(), {
        ...harness.codecs,
        encode_ref: new Proxy(harness.codecs.encode_ref, {}),
      },
    ));
    expectCode("invalid_opaque_ref", () => enumerateAuthorizedSourceImpact(
      input, product, request(), { ...harness.codecs, encode_ref: ({ internal_ref }) => internal_ref },
    ));
  });
});
