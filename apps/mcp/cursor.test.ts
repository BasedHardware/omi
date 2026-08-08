import { createHash, createHmac } from "node:crypto";
import { describe, expect, test } from "bun:test";
import {
  InvalidMcpCursorError,
  MAX_MCP_CURSOR_ENCODED_BYTES,
  asOpaqueVisibleKeyset,
  issueMcpCursor,
  readAfterMcpCursorValidation,
  verifyMcpCursor,
  type McpCursorBindings,
  type McpCursorSigningKeyset,
} from "./cursor";

const OLD_SECRET = new Uint8Array(32).fill(17);
const NEW_SECRET = new Uint8Array(32).fill(29);

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-006)
// domain-pending(DIV-DOMCORE-006)
const rawBindingValues = {
  owner_digest: "owner-private-id",
  app_digest: "application-private-id",
  credential_key_digest: "credential-private-id",
  authorization_generation_digest: "authorization-generation-7",
  grant_generation_digest: "persisted-grant-generation-11",
  account_generation_digest: "account-generation-5",
  graph_generation_digest: "graph-generation-13",
  projection_generation_digest: "projection-generation-17",
  projection_commit_digest: "projection-commit-19",
  visibility_digest: "synthesized-only-visible-set",
  filter_digest: "default-filter",
  query_digest: "private natural-language query",
  cursor_policy_digest: "cursor-policy-v1",
  source_digest: "durable-plus-bounded-stm",
  read_mode_digest: "default-synthesized-read",
} as const;

const bindings = (overrides: Partial<McpCursorBindings> = {}): McpCursorBindings => ({
  ...Object.fromEntries(Object.entries(rawBindingValues).map(([key, value]) => [key, digest(value)])) as unknown as McpCursorBindings,
  ...overrides,
});

const oldKeyset: McpCursorSigningKeyset = {
  active_key_id: "cursor-old",
  keys: [{ key_id: "cursor-old", secret: OLD_SECRET }],
};

const rotatedKeyset: McpCursorSigningKeyset = {
  active_key_id: "cursor-new",
  keys: [
    { key_id: "cursor-new", secret: NEW_SECRET },
    { key_id: "cursor-old", secret: OLD_SECRET },
  ],
};

const opaqueVisibleKeyset = (stableVisibleSortTuple: readonly [number, string]) =>
  asOpaqueVisibleKeyset(`vk1_${digest(JSON.stringify(stableVisibleSortTuple))}`);

const LAST_VISIBLE_KEYSET = opaqueVisibleKeyset([1_799_999_900_000, "visible-item-9"]);

const issue = (keyset: McpCursorSigningKeyset = oldKeyset): string => issueMcpCursor({
  last_visible_key: LAST_VISIBLE_KEYSET,
  bindings: bindings(),
  issued_at_epoch_seconds: 1_800_000_000,
  ttl_seconds: 300,
}, keyset);

const verification = (overrides: Partial<McpCursorBindings> = {}) => ({
  bindings: bindings(overrides),
  now_epoch_seconds: 1_800_000_120,
});

const expectInvalid = (operation: () => unknown): void => {
  try {
    operation();
    throw new Error("expected invalid cursor");
  } catch (error) {
    expect(error).toBeInstanceOf(InvalidMcpCursorError);
    expect((error as InvalidMcpCursorError).name).toBe("InvalidMcpCursorError");
    expect((error as InvalidMcpCursorError).message).toBe("invalid cursor");
    expect((error as InvalidMcpCursorError).code).toBe("invalid_cursor");
  }
};

const resign = (cursor: string, payloadText: string, secret = OLD_SECRET, keyId?: string): string => {
  const [prefix, originalKeyId] = cursor.split(".");
  const selectedKeyId = keyId ?? originalKeyId!;
  const payload = Buffer.from(payloadText, "utf8").toString("base64url");
  const signature = createHmac("sha256", secret)
    .update(`${prefix}.${selectedKeyId}.${payload}`, "ascii")
    .digest("base64url");
  return `${prefix}.${selectedKeyId}.${payload}.${signature}`;
};

const decodedPayload = (cursor: string): Record<string, unknown> => {
  const payload = cursor.split(".")[2]!;
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Record<string, unknown>;
};

describe("MCP signed keyset cursor", () => {
  test("round-trips deterministically with issued/expiry time and an opaque continuation key", () => {
    const first = issue();
    const second = issue();
    const claims = verifyMcpCursor(first, verification(), oldKeyset);

    expect(first).toBe(second);
    expect(first.startsWith("mcp1.cursor-old.")).toBeTrue();
    expect(claims).toEqual({
      version: 1,
      signing_key_id: "cursor-old",
      issued_at_epoch_seconds: 1_800_000_000,
      expires_at_epoch_seconds: 1_800_000_300,
      last_visible_key: LAST_VISIBLE_KEYSET,
      bindings: bindings(),
    });
    expect(Object.isFrozen(claims)).toBeTrue();
    expect(Object.isFrozen(claims.bindings)).toBeTrue();
  });

  test("rotates signing keys without invalidating retained-key cursors", () => {
    const oldCursor = issue(oldKeyset);
    const newCursor = issue(rotatedKeyset);

    expect(verifyMcpCursor(oldCursor, verification(), rotatedKeyset).signing_key_id).toBe("cursor-old");
    expect(verifyMcpCursor(newCursor, verification(), rotatedKeyset).signing_key_id).toBe("cursor-new");
    expect(newCursor.startsWith("mcp1.cursor-new.")).toBeTrue();

    expectInvalid(() => verifyMcpCursor(oldCursor, verification(), {
      active_key_id: "cursor-new",
      keys: [{ key_id: "cursor-new", secret: NEW_SECRET }],
    }));
    expectInvalid(() => verifyMcpCursor(
      oldCursor.replace(".cursor-old.", ".cursor-unknown."),
      verification(),
      rotatedKeyset,
    ));
  });

  test("rejects bitflips, malformed signatures, expiry, and pre-issuance replay with one public error", () => {
    const cursor = issue();
    const [prefix, keyId, payload, signature] = cursor.split(".") as [string, string, string, string];
    const payloadBitflip = `${payload.slice(0, -1)}${payload.at(-1) === "A" ? "B" : "A"}`;
    const signatureBitflip = `${signature.slice(0, -1)}${signature.at(-1) === "A" ? "B" : "A"}`;

    for (const operation of [
      () => verifyMcpCursor(`${prefix}.${keyId}.${payloadBitflip}.${signature}`, verification(), oldKeyset),
      () => verifyMcpCursor(`${prefix}.${keyId}.${payload}.${signatureBitflip}`, verification(), oldKeyset),
      () => verifyMcpCursor(`${prefix}.${keyId}.${payload}.!`, verification(), oldKeyset),
      () => verifyMcpCursor(cursor, { ...verification(), now_epoch_seconds: 1_800_000_300 }, oldKeyset),
      () => verifyMcpCursor(cursor, { ...verification(), now_epoch_seconds: 1_799_999_999 }, oldKeyset),
      () => verifyMcpCursor("legacy-offset-5", verification(), oldKeyset),
    ]) expectInvalid(operation);
  });

  test("binds every authorization, generation, visibility, filter, query, source, and mode digest", () => {
    const cursor = issue();
    let dataCalls = 0;

    for (const key of Object.keys(bindings()) as (keyof McpCursorBindings)[]) {
      expectInvalid(() => readAfterMcpCursorValidation(
        cursor,
        verification({ [key]: digest(`replay-${key}`) }),
        oldKeyset,
        () => { dataCalls++; },
      ));
    }
    expect(dataCalls).toBe(0);

    const result = readAfterMcpCursorValidation(cursor, verification(), oldKeyset, (claims) => {
      dataCalls++;
      return claims.last_visible_key;
    });
    expect(result).toBe(LAST_VISIBLE_KEYSET);
    expect(dataCalls).toBe(1);
  });

  test("payload contains digests and the opaque continuation key, never raw IDs or query text", () => {
    const cursor = issue();
    const serialized = JSON.stringify(decodedPayload(cursor));

    for (const raw of Object.values(rawBindingValues)) expect(serialized).not.toContain(raw);
    expect(serialized).not.toContain("visible-item-9");
    expect(serialized).toContain(bindings().visibility_digest);
    expect(serialized).toContain(LAST_VISIBLE_KEYSET);
    expect(Buffer.byteLength(cursor, "utf8")).toBeLessThanOrEqual(MAX_MCP_CURSOR_ENCODED_BYTES);
  });

  test("accepts only exact canonical plain JSON payloads with bounded fields", () => {
    const cursor = issue();
    const payload = decodedPayload(cursor);
    const bindingsPayload = payload.bindings as Record<string, unknown>;
    const nonCanonical = JSON.stringify(payload, null, 2);
    const unknownTopLevel = JSON.stringify({ ...payload, raw_query: "must-not-survive" });
    const unknownBinding = JSON.stringify({ ...payload, bindings: { ...bindingsPayload, user_id: "must-not-survive" } });
    const malformedDigest = JSON.stringify({ ...payload, bindings: { ...bindingsPayload, query_digest: "not-a-digest" } });
    const oversizedKey = JSON.stringify({ ...payload, last_visible_key: "A".repeat(513) });
    const rawVisibleKey = JSON.stringify({ ...payload, last_visible_key: "raw-owner-id_123" });

    for (const payloadText of [nonCanonical, unknownTopLevel, unknownBinding, malformedDigest, oversizedKey, rawVisibleKey]) {
      expectInvalid(() => verifyMcpCursor(resign(cursor, payloadText), verification(), oldKeyset));
    }
    expect(() => issueMcpCursor({
      last_visible_key: "A".repeat(513) as ReturnType<typeof asOpaqueVisibleKeyset>,
      bindings: bindings(),
      issued_at_epoch_seconds: 1_800_000_000,
      ttl_seconds: 300,
    }, oldKeyset)).toThrow(TypeError);
    expect(() => asOpaqueVisibleKeyset("raw-owner-id_123")).toThrow(TypeError);
    expect(() => issueMcpCursor({
      last_visible_key: "raw-owner-id_123" as ReturnType<typeof asOpaqueVisibleKeyset>,
      bindings: bindings(),
      issued_at_epoch_seconds: 1_800_000_000,
      ttl_seconds: 300,
    }, oldKeyset)).toThrow(TypeError);
  });

  test("rejects signed payloads with impossible or overlong lifetimes", () => {
    const cursor = issue();
    const payload = decodedPayload(cursor);
    const impossible = JSON.stringify({
      ...payload,
      expires_at_epoch_seconds: payload.issued_at_epoch_seconds,
    });
    const overlong = JSON.stringify({
      ...payload,
      expires_at_epoch_seconds: (payload.issued_at_epoch_seconds as number) + 86_401,
    });

    expectInvalid(() => verifyMcpCursor(resign(cursor, impossible), verification(), oldKeyset));
    expectInvalid(() => verifyMcpCursor(resign(cursor, overlong), verification(), oldKeyset));
  });

  test("uses only the stable last visible keyset, so hidden rows cannot perturb the cursor", () => {
    interface PageFixture {
      readonly visible: readonly { readonly sort_time_ms: number; readonly opaque_id: string }[];
      readonly hidden: readonly { readonly sort_time_ms: number; readonly raw_private_id: string }[];
    }
    const cursorForPage = (page: PageFixture): string => {
      const lastVisible = page.visible.at(-1);
      if (!lastVisible) throw new Error("fixture requires a visible row");
      return issueMcpCursor({
        last_visible_key: opaqueVisibleKeyset([lastVisible.sort_time_ms, lastVisible.opaque_id]),
        bindings: bindings(),
        // This is the snapshot read timestamp and is identical for one page.
        issued_at_epoch_seconds: 1_800_000_000,
        ttl_seconds: 300,
      }, oldKeyset);
    };
    const withoutHidden: PageFixture = {
      visible: [{ sort_time_ms: 1_799_999_900_000, opaque_id: "visible-item-9" }],
      hidden: [],
    };
    const withHidden: PageFixture = {
      ...withoutHidden,
      hidden: [{ sort_time_ms: 1_799_999_950_000, raw_private_id: "private-row-must-not-bind" }],
    };
    const changedVisible: PageFixture = {
      visible: [{ sort_time_ms: 1_799_999_910_000, opaque_id: "visible-item-10" }],
      hidden: withHidden.hidden,
    };

    const absentCursor = cursorForPage(withoutHidden);
    const hiddenCursor = cursorForPage(withHidden);
    expect(hiddenCursor).toBe(absentCursor);
    expect(JSON.stringify(decodedPayload(hiddenCursor))).not.toContain("private-row-must-not-bind");
    expect(cursorForPage(changedVisible)).not.toBe(absentCursor);
  });

  test("rejects accessor, inherited, class, and proxy verification inputs without invoking getters or data", () => {
    const cursor = issue();
    let ownerGetterCalls = 0;
    let clockGetterCalls = 0;
    let dataCalls = 0;
    const getterBindings = { ...bindings() };
    Object.defineProperty(getterBindings, "owner_digest", {
      enumerable: true,
      get: () => { ownerGetterCalls++; return digest("cross-owner"); },
    });
    const getterClock = { bindings: bindings() } as Record<string, unknown>;
    Object.defineProperty(getterClock, "now_epoch_seconds", {
      enumerable: true,
      get: () => { clockGetterCalls++; return 1_800_000_301; },
    });
    class VerificationClass {
      bindings = bindings();
      now_epoch_seconds = 1_800_000_120;
    }
    const inherited = Object.create(verification()) as ReturnType<typeof verification>;
    const proxied = new Proxy(verification(), {});

    for (const request of [
      { bindings: getterBindings, now_epoch_seconds: 1_800_000_120 },
      getterClock,
      new VerificationClass(),
      inherited,
      proxied,
    ]) {
      expect(() => readAfterMcpCursorValidation(
        cursor,
        request as ReturnType<typeof verification>,
        oldKeyset,
        () => { dataCalls++; },
      )).toThrow(TypeError);
    }
    expect(ownerGetterCalls).toBe(0);
    expect(clockGetterCalls).toBe(0);
    expect(dataCalls).toBe(0);

    const mutableBindings = { ...bindings() };
    const mutableRequest = { bindings: mutableBindings, now_epoch_seconds: 1_800_000_120 };
    const snapshottedOwner = readAfterMcpCursorValidation(cursor, mutableRequest, oldKeyset, (claims) => {
      mutableBindings.owner_digest = digest("mutated-after-validation");
      mutableRequest.now_epoch_seconds = 1_800_000_301;
      return claims.bindings.owner_digest;
    });
    expect(snapshottedOwner).toBe(bindings().owner_digest);
  });

  test("snapshots issue inputs and signing secrets, and rejects their accessors without invocation", () => {
    let issueGetterCalls = 0;
    let secretGetterCalls = 0;
    let activeKeyGetterCalls = 0;
    const issueBindings = { ...bindings() };
    const mutableSecret = new Uint8Array(32).fill(17);
    const issueRequest = {
      last_visible_key: LAST_VISIBLE_KEYSET,
      bindings: issueBindings,
      issued_at_epoch_seconds: 1_800_000_000,
      ttl_seconds: 300,
    };
    const mutableKeyset: McpCursorSigningKeyset = {
      active_key_id: "cursor-old",
      keys: [{ key_id: "cursor-old", secret: mutableSecret }],
    };
    const cursor = issueMcpCursor(issueRequest, mutableKeyset);

    issueBindings.owner_digest = digest("mutated-owner");
    issueRequest.issued_at_epoch_seconds = 1_800_000_999;
    mutableSecret.fill(0);
    const claims = verifyMcpCursor(cursor, verification(), {
      active_key_id: "cursor-old",
      keys: [{ key_id: "cursor-old", secret: new Uint8Array(32).fill(17) }],
    });
    expect(claims.bindings.owner_digest).toBe(bindings().owner_digest);
    expect(claims.issued_at_epoch_seconds).toBe(1_800_000_000);

    const getterIssueRequest = { ...issueRequest, bindings: bindings() } as Record<string, unknown>;
    Object.defineProperty(getterIssueRequest, "issued_at_epoch_seconds", {
      enumerable: true,
      get: () => { issueGetterCalls++; return 1_800_000_000; },
    });
    const getterKey = { key_id: "cursor-old" } as Record<string, unknown>;
    Object.defineProperty(getterKey, "secret", {
      enumerable: true,
      get: () => { secretGetterCalls++; return OLD_SECRET; },
    });
    const getterKeyset = { keys: oldKeyset.keys } as Record<string, unknown>;
    Object.defineProperty(getterKeyset, "active_key_id", {
      enumerable: true,
      get: () => { activeKeyGetterCalls++; return "cursor-old"; },
    });
    expect(() => issueMcpCursor(
      getterIssueRequest as Parameters<typeof issueMcpCursor>[0],
      oldKeyset,
    )).toThrow(TypeError);
    expect(() => issueMcpCursor(issueRequest, {
      active_key_id: "cursor-old",
      keys: [getterKey as unknown as McpCursorSigningKeyset["keys"][number]],
    })).toThrow(TypeError);
    expect(() => issueMcpCursor(
      issueRequest,
      getterKeyset as unknown as McpCursorSigningKeyset,
    )).toThrow(TypeError);
    expect(() => issueMcpCursor(issueRequest, {
      active_key_id: "cursor-old",
      keys: new Array(0xffff_ffff) as McpCursorSigningKeyset["keys"],
    })).toThrow(TypeError);
    expect(() => issueMcpCursor(issueRequest, {
      active_key_id: "cursor-old",
      keys: [{ key_id: "cursor-old", secret: new Uint8Array(4_097) }],
    })).toThrow(TypeError);
    expect(issueGetterCalls).toBe(0);
    expect(secretGetterCalls).toBe(0);
    expect(activeKeyGetterCalls).toBe(0);
  });
});
