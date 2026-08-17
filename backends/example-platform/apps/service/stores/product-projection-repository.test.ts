import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  birthProductProposition,
  buildProductGroupProjection,
  buildProductProjectionRevision,
  buildProductPropositionRedirect,
} from "../../../core/retrieve/product-projection";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../../core/retrieve/authorization-boundary";
import { snapshot } from "../../../core/retrieve/tree.fixture";
import {
  defineProductProjectionReadRepository,
  defineProductProjectionWriteRepository,
  productProjectionWriteRequestDigest,
  selectLatestAuthorizedProductProjectionPayload,
  type ProductGraphCoordinate,
  type ProductProjectionPayload,
  type ProductProjectionWriteBody,
  type ProductProjectionWriteRequest,
} from "./product-projection-repository";

const digest = (character: string): string => character.repeat(64);

const context = (capability = "memories.project", owner = "owner") =>
  createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: "principal:alice",
    account_id: owner,
    application_id: "app:projector",
    credential_id: "credential:projector",
    credential_generation: 4,
    capability,
    grant_id: "grant:projector",
    grant_version: 9,
    account_epoch: 12,
    destination_activation_revision: 17,
    lifecycle_state: "active",
    deletion_epoch: null,
    authentication_strength: "service-workload",
    issued_at_epoch_seconds: 100,
    expires_at_epoch_seconds: 200,
    authorization_state_digest: digest("a"),
  }, 150);

const authorizationRequest = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner",
    credential_kind: "mcp_api_key",
    app_id: "app:reader",
    key_id: "key:reader",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: "owner",
    consumer: "mcp",
    app_id: "app:reader",
    key_id: "key:reader",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});

const authorizedInput = (): ApplicationGrantProjectedTreeInputSnapshot =>
  readAfterApplicationAuthorization(authorizationRequest(), () => ({
    snapshot: snapshot(),
    options: { account_timezone: "UTC" },
  }));

const productFixture = (input = authorizedInput()) => {
  const claim = input.claims[0]!;
  const born = birthProductProposition({
    owner_account_id: input.owner_account_id,
    proposition_id: "proposition:one",
    birth_claim_lineage_id: claim.claim_lineage_id,
    origin: "native",
    graph_frontier: input.graph_generation,
    input_digest: digest("b"),
    result_digest: digest("c"),
    created_at_event_time: 10,
  });
  const renderedContent = Object.freeze({
    title: "A cited memory",
    fields: Object.freeze(["one", "two"]),
  });
  const renderedContentDigest = sha256CanonicalContent(renderedContent);
  const projection = buildProductProjectionRevision({
    identity: born.identity,
    membership: born.membership,
    projection_sequence: 1,
    graph_frontier: input.graph_generation,
    renderer_contract_digest: digest("d"),
    rendered_content_digest: renderedContentDigest,
    citations: [{
      claim_lineage_id: claim.claim_lineage_id,
      claim_revision_id: claim.claim_revision_id,
      evidence_refs: [...claim.evidence_refs].sort(),
    }],
    created_at_event_time: 20,
  });
  const payload: ProductProjectionPayload = {
    owner_account_id: input.owner_account_id,
    projection_revision_id: projection.projection_revision_id,
    rendered_content_digest: renderedContentDigest,
    payload_contract_version: "memory-card-v1",
    rendered_content: renderedContent,
  };
  const graph: ProductGraphCoordinate = {
    owner_account_id: input.owner_account_id,
    graph_frontier: input.graph_generation,
    graph_commit_id: "commit:one",
    graph_commit_sequence: 1,
  };
  return { input, claim, born, projection, payload, graph };
};

const request = <Body extends ProductProjectionWriteBody>(body: Body): Body & { request_digest: string } => ({
  ...body,
  request_digest: productProjectionWriteRequestDigest(body),
});

describe("sealed projector write repository", () => {
  test("accepts a complete birth through the projector capability only", async () => {
    const fixture = productFixture();
    const calls: unknown[] = [];
    const repository = defineProductProjectionWriteRepository(async (authorized, normalized) => {
      calls.push([authorized, normalized]);
      return { kind: "appended" };
    });
    const body = {
      operation: "birth" as const,
      graph: fixture.graph,
      identity: fixture.born.identity,
      membership: fixture.born.membership,
    };
    await expect(repository.append(context(), request(body))).resolves.toEqual({ kind: "appended" });
    await expect(repository.append(context("memories.write"), request(body))).rejects.toThrow("capability_denied");
    expect(calls).toHaveLength(1);
    expect(Object.keys(repository).sort()).toEqual(["append"]);
    expect("query" in repository).toBe(false);
    expect("execute" in repository).toBe(false);
  });

  test("legacy mapping births remain outside projector authority", async () => {
    const fixture = productFixture();
    let calls = 0;
    const repository = defineProductProjectionWriteRepository(async () => {
      calls += 1;
      return { kind: "appended" };
    });
    const identity = { ...fixture.born.identity, origin: "legacy_mapping" as const };
    await expect(repository.append(context(), request({
      operation: "birth", graph: fixture.graph, identity, membership: fixture.born.membership,
    }))).rejects.toThrow("invalid_birth");
    expect(calls).toBe(0);
  });

  test("projection writes bind graph, membership, citations, payload, and request digest", async () => {
    const fixture = productFixture();
    let calls = 0;
    const repository = defineProductProjectionWriteRepository(async () => {
      calls += 1;
      return { kind: "replayed" };
    });
    const body = {
      operation: "projection" as const,
      graph: fixture.graph,
      identity: fixture.born.identity,
      membership: fixture.born.membership,
      projection: fixture.projection,
      payload: fixture.payload,
    };
    await expect(repository.append(context(), request(body))).resolves.toEqual({ kind: "replayed" });

    const changedPayload = {
      ...fixture.payload,
      payload_contract_version: "memory-card-v2",
    };
    expect(productProjectionWriteRequestDigest({ ...body, payload: changedPayload }))
      .not.toBe(productProjectionWriteRequestDigest(body));
    await expect(repository.append(context(), {
      ...body,
      payload: changedPayload,
      request_digest: productProjectionWriteRequestDigest(body),
    })).rejects.toThrow("request_digest_mismatch");
    await expect(repository.append(context(), request({
      ...body,
      graph: { ...fixture.graph, graph_frontier: "frontier:stale" },
    }))).rejects.toThrow("coordinate_mismatch");
    expect(calls).toBe(1);
  });

  test("payload parsing is bounded, strict, content-addressed, and runs before the adapter", async () => {
    const fixture = productFixture();
    let calls = 0;
    const repository = defineProductProjectionWriteRepository(async () => {
      calls += 1;
      return { kind: "appended" };
    });
    const body = {
      operation: "projection" as const,
      graph: fixture.graph,
      identity: fixture.born.identity,
      membership: fixture.born.membership,
      projection: fixture.projection,
      payload: fixture.payload,
    };
    const badDigest = { ...fixture.payload, rendered_content_digest: digest("f") };
    await expect(repository.append(context(), request({ ...body, payload: badDigest })))
      .rejects.toThrow("payload_digest_mismatch");

    const proxied = { ...fixture.payload, rendered_content: new Proxy({ safe: true }, {}) };
    await expect(repository.append(context(), {
      ...body,
      payload: proxied,
      request_digest: digest("0"),
    } as ProductProjectionWriteRequest))
      .rejects.toThrow("invalid_payload");

    const accessorContent = {};
    Object.defineProperty(accessorContent, "secret", {
      enumerable: true,
      get: () => { throw new Error("must not execute"); },
    });
    const accessorPayload = { ...fixture.payload, rendered_content: accessorContent };
    await expect(repository.append(context(), {
      ...body,
      payload: accessorPayload,
      request_digest: digest("0"),
    } as ProductProjectionWriteRequest)).rejects.toThrow("invalid_payload");

    const oversized = { ...fixture.payload, rendered_content: { text: "x".repeat(256 * 1024) } };
    await expect(repository.append(context(), request({ ...body, payload: oversized })))
      .rejects.toThrow("payload_too_large");
    expect(calls).toBe(0);
  });

  test("closed redirect and group operations are re-parsed without exposing SQL", async () => {
    const fixture = productFixture();
    const second = birthProductProposition({
      owner_account_id: "owner",
      proposition_id: "proposition:two",
      birth_claim_lineage_id: fixture.claim.claim_lineage_id,
      origin: "native",
      graph_frontier: fixture.input.graph_generation,
      input_digest: digest("7"),
      result_digest: digest("8"),
      created_at_event_time: 30,
    });
    const redirect = buildProductPropositionRedirect({
      owner_account_id: "owner",
      source_proposition_id: fixture.born.identity.proposition_id,
      successor_proposition_ids: [second.identity.proposition_id],
      operation: "merge",
      operation_ref: "operation:merge",
      created_at_event_time: 40,
    });
    const group = buildProductGroupProjection({
      owner_account_id: "owner",
      proposition_ids: [fixture.born.identity.proposition_id, second.identity.proposition_id].sort(),
      input_frontier: fixture.input.graph_generation,
      projection_contract_digest: digest("9"),
      result_digest: digest("e"),
      created_at_event_time: 50,
    });
    const operations: string[] = [];
    const repository = defineProductProjectionWriteRepository(async (_context, normalized) => {
      operations.push(normalized.operation);
      return { kind: "appended" };
    });
    await repository.append(context(), request({ operation: "redirect", graph: fixture.graph, redirect }));
    await repository.append(context(), request({ operation: "group", graph: fixture.graph, group }));
    expect(operations).toEqual(["redirect", "group"]);
  });

  test("hostile request containers and owner substitution fail before an adapter call", async () => {
    const fixture = productFixture();
    let calls = 0;
    const repository = defineProductProjectionWriteRepository(async () => {
      calls += 1;
      return { kind: "appended" };
    });
    const body = {
      operation: "birth" as const,
      graph: fixture.graph,
      identity: fixture.born.identity,
      membership: fixture.born.membership,
    };
    await expect(repository.append(context(), new Proxy(request(body), {
      get: () => { throw new Error("must not execute"); },
    }))).rejects.toThrow("invalid_request");
    await expect(repository.append(context(), request({
      ...body,
      graph: { ...fixture.graph, owner_account_id: "owner:bob" },
    }))).rejects.toThrow("owner_mismatch");
    expect(calls).toBe(0);
  });
});

describe("authorized product projection reads", () => {
  test("loads only from the branded read snapshot and returns its cited payload", async () => {
    const fixture = productFixture();
    let calls = 0;
    const repository = defineProductProjectionReadRepository(async (input) => {
      calls += 1;
      expect(input).toBe(fixture.input);
      return {
        identities: [fixture.born.identity],
        memberships: [fixture.born.membership],
        projections: [fixture.projection],
        payloads: [fixture.payload],
      };
    });
    const loaded = await repository.loadAuthorized(fixture.input);
    const selected = selectLatestAuthorizedProductProjectionPayload(fixture.born.identity, loaded);
    expect(selected?.projection.projection_revision_id).toBe(fixture.projection.projection_revision_id);
    expect(selected?.payload.rendered_content).toEqual(fixture.payload.rendered_content);
    expect(loaded.reader_projection_digest).toBe(fixture.input.reader_projection_digest);
    expect(calls).toBe(1);

    const forged = structuredClone(fixture.input) as ApplicationGrantProjectedTreeInputSnapshot;
    await expect(repository.loadAuthorized(forged)).rejects.toThrow("unauthorized_read_input");
    expect(calls).toBe(1);
  });

  test("missing, duplicate, extra, or digest-drifted payloads fail closed", async () => {
    const fixture = productFixture();
    const base = {
      identities: [fixture.born.identity],
      memberships: [fixture.born.membership],
      projections: [fixture.projection],
    };
    await expect(defineProductProjectionReadRepository(async () => ({ ...base, payloads: [] }))
      .loadAuthorized(fixture.input)).rejects.toThrow("payload_projection_mismatch");
    await expect(defineProductProjectionReadRepository(async () => ({
      ...base,
      payloads: [fixture.payload, fixture.payload],
    })).loadAuthorized(fixture.input)).rejects.toThrow("duplicate_payload");
    await expect(defineProductProjectionReadRepository(async () => ({
      ...base,
      payloads: [{ ...fixture.payload, rendered_content: { changed: true } }],
    })).loadAuthorized(fixture.input)).rejects.toThrow("payload_digest_mismatch");
    await expect(defineProductProjectionReadRepository(async () => ({
      ...base,
      payloads: [{ ...fixture.payload, projection_revision_id: "projection:extra" }],
    })).loadAuthorized(fixture.input)).rejects.toThrow("payload_projection_mismatch");
  });

  test("unused identity or membership rows cannot leak through an authorized read", async () => {
    const fixture = productFixture();
    const extra = birthProductProposition({
      owner_account_id: fixture.input.owner_account_id,
      proposition_id: "proposition:unused",
      birth_claim_lineage_id: fixture.claim.claim_lineage_id,
      origin: "native",
      graph_frontier: fixture.input.graph_generation,
      input_digest: digest("1"),
      result_digest: digest("2"),
      created_at_event_time: 30,
    });
    const base = {
      identities: [fixture.born.identity],
      memberships: [fixture.born.membership],
      projections: [fixture.projection],
      payloads: [fixture.payload],
    };
    await expect(defineProductProjectionReadRepository(async () => ({
      ...base,
      identities: [...base.identities, extra.identity],
    })).loadAuthorized(fixture.input)).rejects.toThrow("read_row_closure_mismatch");
    await expect(defineProductProjectionReadRepository(async () => ({
      ...base,
      memberships: [...base.memberships, extra.membership],
    })).loadAuthorized(fixture.input)).rejects.toThrow("read_row_closure_mismatch");
  });

  test("cross-owner or authorization-invisible citation rows are rejected after loading", async () => {
    const fixture = productFixture();
    const foreignIdentity = { ...fixture.born.identity, owner_account_id: "owner:bob" };
    await expect(defineProductProjectionReadRepository(async () => ({
      identities: [foreignIdentity],
      memberships: [fixture.born.membership],
      projections: [fixture.projection],
      payloads: [fixture.payload],
    })).loadAuthorized(fixture.input)).rejects.toThrow("owner_mismatch");

    const hiddenProjection = buildProductProjectionRevision({
      identity: fixture.born.identity,
      membership: fixture.born.membership,
      projection_sequence: 2,
      graph_frontier: fixture.input.graph_generation,
      renderer_contract_digest: digest("d"),
      rendered_content_digest: fixture.payload.rendered_content_digest,
      citations: [{
        claim_lineage_id: fixture.claim.claim_lineage_id,
        claim_revision_id: "claim:hidden",
        evidence_refs: ["evidence:hidden"],
      }],
      created_at_event_time: 21,
    });
    await expect(defineProductProjectionReadRepository(async () => ({
      identities: [fixture.born.identity],
      memberships: [fixture.born.membership],
      projections: [hiddenProjection],
      payloads: [{ ...fixture.payload, projection_revision_id: hiddenProjection.projection_revision_id }],
    })).loadAuthorized(fixture.input)).rejects.toThrow("invalid_projection");
  });
});
