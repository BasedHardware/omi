import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import {
  projectApplicationDefaultReadTreeInputFromAuthorizationEvidence,
} from "../../../core/retrieve/authorization-boundary";
import { snapshot } from "../../../core/retrieve/tree.fixture";
import { produceQaRenders } from "../../qa/renders";
import { createQaCursorAdapter } from "../../qa/cursor-bindings";
import {
  exportDirectAuthorizedMemories,
  readDirectAuthorizedMemoryPage,
  type DirectAuthorizedMemoryProjectionLoad,
} from "./memory-read";

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");

const load = (
  suffix = "a",
  dbNowEpochSeconds = 1_800_000_000,
): DirectAuthorizedMemoryProjectionLoad => {
  const principal = digest(`principal:${suffix}`);
  const authorization = digest(`authorization:${suffix}`);
  const grant = digest(`grant:${suffix}`);
  const projected = projectApplicationDefaultReadTreeInputFromAuthorizationEvidence(
    snapshot(),
    { account_timezone: "UTC" },
    {
      owner_account_id: "owner",
      app_id: "app:product",
      key_id: "credential:product",
      principal_digest: principal,
      authorization_digest: authorization,
      persisted_grant_state_digest: grant,
    },
  );
  return {
    projected,
    owner_identity_digest: digest("owner"),
    application_identity_digest: digest("application"),
    credential_identity_digest: digest("credential"),
    authorization_generation_digest: authorization,
    grant_state_digest: grant,
    account_generation_digest: digest(`account:${suffix}`),
    db_now_epoch_seconds: dbNowEpochSeconds,
  };
};

const config = (
  loads: readonly DirectAuthorizedMemoryProjectionLoad[],
  sequence: string[],
  traces: unknown[],
  cursor?: ReturnType<typeof createQaCursorAdapter>,
) => {
  let index = 0;
  return {
    loadAuthorized: async () => {
      sequence.push("authorized-load");
      return loads[Math.min(index++, loads.length - 1)]!;
    },
    produceRenders: async (projected: DirectAuthorizedMemoryProjectionLoad["projected"]) => {
      sequence.push("render");
      return produceQaRenders(projected);
    },
    codecRootSecret: new Uint8Array(32).fill(0x41),
    verifyCursor: cursor?.verifyCursor ?? (() => { throw new Error("cursor verification must not run"); }),
    issueCursor: cursor?.issueCursor ?? (() => { throw new Error("cursor issue must not run"); }),
    traceSink: (trace: unknown) => { sequence.push("trace"); traces.push(trace); },
    acceptedCoverageState: "no_eligible" as const,
    stmCoverageState: "no_eligible" as const,
    granularity: "all_nodes" as const,
  };
};

describe("direct Firebase/PostgreSQL-authorized memory read", () => {
  test("renders from the authorized graph and revalidates after renderer I/O before release", async () => {
    const sequence: string[] = [];
    const traces: unknown[] = [];
    const stable = load("a");
    const result = await readDirectAuthorizedMemoryPage(
      { limit: 100, cursor: null },
      config([stable, load("a", 1_800_000_001), load("a", 1_800_000_002)], sequence, traces),
    );
    const page = parseSynthesizedPageJson(result.canonical_json);
    expect(page).not.toBeNull();
    expect(page!.items.length).toBeGreaterThan(0);
    expect(sequence).toEqual([
      "authorized-load", "render", "authorized-load", "authorized-load", "trace",
    ]);
    expect(traces).toHaveLength(1);
  });

  test("repeated revocation after rendering releases no page, cursor, or trace", async () => {
    const sequence: string[] = [];
    const traces: unknown[] = [];
    const stable = load("a");
    const revoked = load("revoked");
    await expect(readDirectAuthorizedMemoryPage(
      { limit: 100, cursor: null },
      config([stable, revoked, stable, revoked], sequence, traces),
    )).rejects.toThrow("application read invalidated during revalidation");
    expect(sequence).toEqual([
      "authorized-load", "render", "authorized-load",
      "authorized-load", "render", "authorized-load",
    ]);
    expect(traces).toEqual([]);
  });

  test("a cursor binds the exact direct authority and projection generations", async () => {
    const cursor = createQaCursorAdapter({
      signing_keyset: {
        active_key_id: "direct-product",
        keys: [{ key_id: "direct-product", secret: new Uint8Array(32).fill(0x71) }],
      },
    });
    const stable = load("a");
    const first = await readDirectAuthorizedMemoryPage(
      { limit: 1, cursor: null },
      config([stable, stable, stable], [], [], cursor),
    );
    const firstPage = parseSynthesizedPageJson(first.canonical_json)!;
    expect(firstPage.window.nextCursor).not.toBeNull();

    const second = await readDirectAuthorizedMemoryPage(
      { limit: 1, cursor: firstPage.window.nextCursor },
      config([stable, stable, stable], [], [], cursor),
    );
    const secondPage = parseSynthesizedPageJson(second.canonical_json)!;
    expect(secondPage.items[0]!.id).not.toBe(firstPage.items[0]!.id);

    const changed = load("changed-authority");
    await expect(readDirectAuthorizedMemoryPage(
      { limit: 1, cursor: firstPage.window.nextCursor },
      config([changed, changed, changed], [], [], cursor),
    )).rejects.toThrow("invalid cursor");
  });

  test("a final authority change after core page construction discards buffered trace and bytes", async () => {
    const sequence: string[] = [];
    const traces: unknown[] = [];
    const stable = load("a");
    const revoked = load("revoked");
    await expect(readDirectAuthorizedMemoryPage(
      { limit: 100, cursor: null },
      config([stable, stable, revoked, stable, stable, revoked], sequence, traces),
    )).rejects.toThrow("application read invalidated during revalidation");
    expect(sequence.filter((entry) => entry === "authorized-load")).toHaveLength(6);
    expect(sequence.filter((entry) => entry === "trace")).toHaveLength(0);
    expect(traces).toEqual([]);
  });
});

describe("direct Firebase/PostgreSQL-authorized memory export", () => {
  test("exports complete lineage only after final authority revalidation", async () => {
    const sequence: string[] = [];
    const stable = load("export");
    let index = 0;
    const exported = await exportDirectAuthorizedMemories({
      loadAuthorized: async () => {
        sequence.push("authorized-load");
        return [stable, load("export", 1_800_000_001), load("export", 1_800_000_002)][index++]!;
      },
      produceRenders: async (projected) => {
        sequence.push("render");
        return produceQaRenders(projected);
      },
      codecRootSecret: new Uint8Array(32).fill(0x52),
      chunkMaxBytes: 64 * 1024,
    });
    expect(sequence).toEqual(["authorized-load", "render", "authorized-load", "authorized-load"]);
    expect(exported.manifest.counts).toEqual({ memories: 1, lineages: 1, sources: 1, chunks: 1 });
    expect(exported.chunk_json[0]).toContain("evidence");
    expect(exported.chunk_json[0]).not.toContain("lineage:a");
  });

  test("a late authority change releases no export bundle", async () => {
    const stable = load("export");
    const revoked = load("revoked");
    const loads = [stable, stable, revoked, stable, stable, revoked];
    let index = 0;
    await expect(exportDirectAuthorizedMemories({
      loadAuthorized: async () => loads[index++]!,
      produceRenders: produceQaRenders,
      codecRootSecret: new Uint8Array(32).fill(0x52),
      chunkMaxBytes: 64 * 1024,
    })).rejects.toThrow("application read invalidated during revalidation");
    expect(index).toBe(6);
  });
});
