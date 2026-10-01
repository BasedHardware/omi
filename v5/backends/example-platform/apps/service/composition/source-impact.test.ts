import { describe, expect, test } from "bun:test";

import {
  birthProductProposition,
  buildProductProjectionRevision,
} from "../../../core/retrieve/product-projection";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  SourceImpactError,
  type SourceImpactPageRequest,
} from "../../../core/retrieve/source-impact";
import type { GraphSnapshot } from "../../../core/retrieve";
import type { ApplicationMemoryReadAuthorizationRequest } from
  "../../../core/retrieve/authorization-boundary";
import { snapshot } from "../../../core/retrieve/tree.fixture";
import {
  defineProductProjectionReadRepository,
  type ProductProjectionPayload,
  type ProductProjectionReadRepository,
} from "../stores/product-projection-repository";
import {
  SourceImpactServiceError,
  createAuthorizedSourceImpactReader,
  type AuthorizedSourceImpactReaderConfig,
} from "./source-impact";

const digest = (character: string): string => character.repeat(64);

const request = (overrides: Partial<SourceImpactPageRequest> = {}): SourceImpactPageRequest => ({
  target: { kind: "capture_session", capture_session_id: "capture" },
  limit: 100,
  cursor: null,
  ...overrides,
});

const authorization = (
  keyId = "key:reader",
  enabled = true,
): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner",
    credential_kind: "mcp_api_key",
    app_id: "app:source-impact",
    key_id: keyId,
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: "owner",
    consumer: "mcp",
    app_id: "app:source-impact",
    key_id: keyId,
    enabled,
    default_read: true,
    scopes: ["memories.read"],
  },
});

const hiddenVariant = (): GraphSnapshot => {
  const base = snapshot();
  const hiddenEvent = {
    revision_id: "event:hidden-source-impact",
    event: {
      ...base.events![0]!.event,
      event_id: "event:hidden-source-impact",
      event_revision_id: "event:hidden-source-impact",
      evidence_addressable_refs: ["evidence:hidden-source-impact"],
    },
  };
  const hiddenEvidence = {
    revision_id: "evidence:hidden-source-impact:r1",
    evidence: {
      ...base.evidence![0]!.evidence,
      evidence_id: "evidence:hidden-source-impact",
      event_revision_id: hiddenEvent.event.event_revision_id,
      excerpt: "raw hidden source impact sentinel",
      state: "security_hidden" as const,
      policy_labels: ["sensitivity:private"],
    },
  };
  return {
    ...base,
    claims: base.claims.map((entry) => entry.revision_id === "private" ? {
      ...entry,
      claim: { ...entry.claim, evidence_refs: [hiddenEvidence.evidence.evidence_id] },
    } : entry),
    events: [...base.events!, hiddenEvent],
    evidence: [...base.evidence!, hiddenEvidence],
  };
};

const productRows = (
  input: Parameters<ProductProjectionReadRepository["loadAuthorized"]>[0],
  sequence = 1,
) => {
  const claim = input.claims[0]!;
  const born = birthProductProposition({
    owner_account_id: input.owner_account_id,
    proposition_id: "proposition:source-impact",
    birth_claim_lineage_id: claim.claim_lineage_id,
    origin: "native",
    graph_frontier: input.graph_generation,
    input_digest: digest("a"),
    result_digest: digest("b"),
    created_at_event_time: 10,
  });
  const renderedContent = Object.freeze({ sequence });
  const renderedContentDigest = sha256CanonicalContent(renderedContent);
  const projection = buildProductProjectionRevision({
    identity: born.identity,
    membership: born.membership,
    projection_sequence: sequence,
    graph_frontier: input.graph_generation,
    renderer_contract_digest: digest("c"),
    rendered_content_digest: renderedContentDigest,
    citations: [{
      claim_lineage_id: claim.claim_lineage_id,
      claim_revision_id: claim.claim_revision_id,
      evidence_refs: [...claim.evidence_refs].sort(),
    }],
    created_at_event_time: 20 + sequence,
  });
  const payload: ProductProjectionPayload = {
    owner_account_id: input.owner_account_id,
    projection_revision_id: projection.projection_revision_id,
    rendered_content_digest: renderedContentDigest,
    payload_contract_version: "source-impact-test-v1",
    rendered_content: renderedContent,
  };
  return {
    identities: [born.identity],
    memberships: [born.membership],
    projections: [projection],
    payloads: [payload],
  };
};

interface Fixture {
  readonly config: AuthorizedSourceImpactReaderConfig;
  readonly counts: { authorization: number; coherent: number; product: number };
  readonly secret: Uint8Array;
}

const fixture = (options: {
  readonly keyId?: string;
  readonly snapshots?: readonly GraphSnapshot[];
  readonly projectionSequence?: (call: number) => number;
  readonly revokeDuringProductCall?: number;
} = {}): Fixture => {
  const counts = { authorization: 0, coherent: 0, product: 0 };
  const secret = new Uint8Array(32).fill(37);
  let grantEnabled = true;
  const snapshots = options.snapshots ?? [snapshot()];
  const repository = defineProductProjectionReadRepository(async (input) => {
    counts.product += 1;
    if (counts.product === options.revokeDuringProductCall) grantEnabled = false;
    return productRows(input, options.projectionSequence?.(counts.product) ?? 1);
  });
  return {
    counts,
    secret,
    config: {
      resolveAuthorization: () => {
        counts.authorization += 1;
        return authorization(options.keyId, grantEnabled);
      },
      loadCoherent: () => {
        const selected = snapshots[Math.min(counts.coherent, snapshots.length - 1)]!;
        counts.coherent += 1;
        return { durable_snapshot: selected, account_timezone: "UTC" };
      },
      productProjectionRepository: repository,
      codecRootSecret: secret,
    },
  };
};

const expectServiceCode = async (
  code: SourceImpactServiceError["code"],
  operation: () => Promise<unknown>,
): Promise<void> => {
  try {
    await operation();
    throw new Error("expected source-impact service error");
  } catch (error) {
    expect(error).toBeInstanceOf(SourceImpactServiceError);
    expect((error as SourceImpactServiceError).code).toBe(code);
    expect((error as Error).message).toBe(code);
  }
};

describe("authorized source-impact service composition", () => {
  test("emits only after two complete loads and redeems stateless cursors across readers", async () => {
    const firstFixture = fixture();
    const firstReader = createAuthorizedSourceImpactReader(firstFixture.config);
    const first = await firstReader.read(request({ limit: 2 }));
    expect(first.items).toHaveLength(2);
    expect(first.next_cursor).toMatch(/^sic1_[a-f0-9]{64}$/);
    expect(firstFixture.counts).toEqual({ authorization: 4, coherent: 2, product: 2 });
    const serialized = JSON.stringify(first);
    for (const raw of ["owner", "capture", "lineage:a", "proposition:source-impact"]) {
      expect(serialized).not.toContain(raw);
    }

    const independentFixture = fixture();
    const second = await createAuthorizedSourceImpactReader(independentFixture.config).read(request({
      limit: 2,
      cursor: first.next_cursor,
    }));
    expect(second.items).toHaveLength(2);
    expect(new Set([...first.items, ...second.items].map((item) => item.ref)).size).toBe(4);
    expect(independentFixture.counts).toEqual({ authorization: 4, coherent: 2, product: 2 });
  });

  test("revocation during product I/O fails the post-repository fence content-safely", async () => {
    const revoked = fixture({ revokeDuringProductCall: 1 });
    const reader = createAuthorizedSourceImpactReader(revoked.config);
    await expectServiceCode("read_unavailable", () => reader.read(request()));
    expect(revoked.counts).toEqual({ authorization: 2, coherent: 1, product: 1 });
  });

  test("one cited-product drift retries wholly while repeated drift is invalidated", async () => {
    const converging = fixture({ projectionSequence: (call) => call === 1 ? 1 : 2 });
    const page = await createAuthorizedSourceImpactReader(converging.config).read(request());
    expect(page.items.some((item) => item.kind === "product_projection")).toBe(true);
    expect(converging.counts).toEqual({ authorization: 8, coherent: 4, product: 4 });

    const drifting = fixture({ projectionSequence: (call) => call });
    await expectServiceCode("read_invalidated", () =>
      createAuthorizedSourceImpactReader(drifting.config).read(request()));
    expect(drifting.counts).toEqual({ authorization: 8, coherent: 4, product: 4 });
  });

  test("an upstream hidden-row change is byte-noninterfering and does not retry", async () => {
    const changing = fixture({ snapshots: [snapshot(), hiddenVariant()] });
    const hidden = await createAuthorizedSourceImpactReader(changing.config).read(request());
    const stable = await createAuthorizedSourceImpactReader(fixture().config).read(request());
    expect(hidden).toEqual(stable);
    expect(changing.counts).toEqual({ authorization: 4, coherent: 2, product: 2 });
    expect(JSON.stringify(hidden)).not.toContain("hidden-source-impact");
    expect(JSON.stringify(hidden)).not.toContain("raw hidden source impact sentinel");
  });

  test("reader/grant-bound cursors and refs cannot cross credentials", async () => {
    const ownerReader = createAuthorizedSourceImpactReader(fixture({ keyId: "key:a" }).config);
    const first = await ownerReader.read(request({ limit: 2 }));
    const otherReader = createAuthorizedSourceImpactReader(fixture({ keyId: "key:b" }).config);
    await expect(otherReader.read(request({ limit: 2, cursor: first.next_cursor })))
      .rejects.toMatchObject({ name: "SourceImpactError", code: "invalid_cursor" });
    const otherFirst = await otherReader.read(request({ limit: 2 }));
    expect(otherFirst.items.map((item) => item.ref)).not.toEqual(first.items.map((item) => item.ref));
    expect(otherFirst.snapshot_digest).not.toBe(first.snapshot_digest);
    expect(otherFirst.query_digest).not.toBe(first.query_digest);
  });

  test("validates requests/config before loading and snapshots caller secret bytes", async () => {
    const stable = fixture();
    const reader = createAuthorizedSourceImpactReader(stable.config);
    stable.secret.fill(0);
    const page = await reader.read(request());
    const independent = await createAuthorizedSourceImpactReader(fixture().config).read(request());
    expect(page).toEqual(independent);

    const noLoad = fixture();
    const invalidReader = createAuthorizedSourceImpactReader(noLoad.config);
    await expect(invalidReader.read({ ...request(), limit: 0 })).rejects.toBeInstanceOf(SourceImpactError);
    expect(noLoad.counts).toEqual({ authorization: 0, coherent: 0, product: 0 });

    expect(() => createAuthorizedSourceImpactReader({
      ...fixture().config,
      codecRootSecret: new Uint8Array(31),
    })).toThrow(SourceImpactServiceError);
    expect(() => createAuthorizedSourceImpactReader({
      ...fixture().config,
      resolveAuthorization: new Proxy(() => authorization(), {}),
    })).toThrow(SourceImpactServiceError);
    expect(() => createAuthorizedSourceImpactReader({
      ...fixture().config,
      productProjectionRepository: {
        loadAuthorized: async () => { throw new Error("raw forged repository"); },
      } as unknown as ProductProjectionReadRepository,
    })).toThrow(SourceImpactServiceError);

    let configGetterCalls = 0;
    const accessorConfig = { ...fixture().config } as Record<string, unknown>;
    Object.defineProperty(accessorConfig, "codecRootSecret", {
      enumerable: true,
      get: () => {
        configGetterCalls += 1;
        return new Uint8Array(32);
      },
    });
    expect(() => createAuthorizedSourceImpactReader(
      accessorConfig as unknown as AuthorizedSourceImpactReaderConfig,
    )).toThrow(SourceImpactServiceError);
    expect(configGetterCalls).toBe(0);

    let snapshotGetterCalls = 0;
    const hostileLoad = fixture();
    const hostileReader = createAuthorizedSourceImpactReader({
      ...hostileLoad.config,
      loadCoherent: () => {
        const wrapper = { account_timezone: "UTC" } as Record<string, unknown>;
        Object.defineProperty(wrapper, "durable_snapshot", {
          enumerable: true,
          get: () => {
            snapshotGetterCalls += 1;
            return snapshot();
          },
        });
        return wrapper as unknown as ReturnType<AuthorizedSourceImpactReaderConfig["loadCoherent"]>;
      },
    });
    await expectServiceCode("read_unavailable", () => hostileReader.read(request()));
    expect(snapshotGetterCalls).toBe(0);
  });
});
