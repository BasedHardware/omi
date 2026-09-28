import { describe, expect, test } from "bun:test";

import { evaluateGates } from "../src/gates";
import type { MetricSample } from "../src/types";

const sample = (
  scope: string,
  hits: readonly { id: string; score: number }[],
  opts: {
    relevantDocIds?: readonly string[];
    revokedAtQueryTime?: ReadonlySet<string>;
  } = {}
): MetricSample => ({
  queryId: `q-${scope}-${hits[0]?.id ?? "none"}`,
  scope: { accountId: scope },
  relevantDocIds: opts.relevantDocIds ?? [],
  hits,
  latencyMs: 1,
  indexLagMs: 0,
  revokedIdsAtQueryTime: opts.revokedAtQueryTime ?? new Set(),
});

const accountDocs = (
  entries: ReadonlyArray<readonly [string, readonly string[]]>
) =>
  new Map<string, ReadonlySet<string>>(
    entries.map(([account, ids]) => [account, new Set(ids)])
  );

describe("account-isolation hard gate", () => {
  test("passes when every hit belongs to the querying account", () => {
    const result = evaluateGates(
      [sample("acct-synthetic-alpha", [{ id: "alpha-1", score: 1 }])],
      accountDocs([
        ["acct-synthetic-alpha", ["alpha-1", "alpha-2"]],
        ["acct-synthetic-beta", ["beta-1"]],
      ])
    );
    expect(result.passed).toBe(true);
  });

  test("fails when any hit id is foreign to the querying account", () => {
    const result = evaluateGates(
      [sample("acct-synthetic-alpha", [{ id: "beta-1", score: 1 }])],
      accountDocs([
        ["acct-synthetic-alpha", ["alpha-1"]],
        ["acct-synthetic-beta", ["beta-1"]],
      ])
    );
    expect(result.passed).toBe(false);
    if (!result.passed) {
      expect(result.reasons.join("\n")).toContain("foreign");
    }
  });
});

describe("deletion-correctness hard gate", () => {
  test("passes when no revoked id appears in results taken after deletion", () => {
    const revoked = new Set(["alpha-2"]);
    const result = evaluateGates(
      [
        sample("acct-synthetic-alpha", [{ id: "alpha-1", score: 1 }], {
          revokedAtQueryTime: revoked,
        }),
      ],
      accountDocs([["acct-synthetic-alpha", ["alpha-1", "alpha-2"]]])
    );
    expect(result.passed).toBe(true);
  });

  test("fails when a revoked id is returned after deletion", () => {
    const revoked = new Set(["alpha-2"]);
    const result = evaluateGates(
      [
        sample("acct-synthetic-alpha", [{ id: "alpha-2", score: 1 }], {
          revokedAtQueryTime: revoked,
        }),
      ],
      accountDocs([["acct-synthetic-alpha", ["alpha-1", "alpha-2"]]])
    );
    expect(result.passed).toBe(false);
    if (!result.passed) {
      expect(result.reasons.join("\n")).toContain("revoked");
    }
  });

  test("does not flag a revoked id returned before it was revoked", () => {
    const result = evaluateGates(
      [
        sample("acct-synthetic-alpha", [{ id: "alpha-2", score: 1 }], {
          revokedAtQueryTime: new Set(),
        }),
      ],
      accountDocs([["acct-synthetic-alpha", ["alpha-1", "alpha-2"]]])
    );
    expect(result.passed).toBe(true);
  });
});

describe("gate sensitivity", () => {
  test("an intentionally bad provider fails both gates", async () => {
    const { buildSyntheticCorpus } = await import("../src/corpus");
    const { runWorkload } = await import("../src/harness");
    const { createBadProvider } = await import("../src/providers/bad");
    const corpus = buildSyntheticCorpus();
    const bad = createBadProvider();
    const { samples } = await runWorkload(bad, corpus, {
      k: 5,
      deleteCount: 2,
    });
    const docs = accountDocs(
      corpus.docs.map((doc) => [doc.accountId, [doc.id]] as const)
    );
    const merged = new Map<string, ReadonlySet<string>>();
    for (const [account, ids] of docs) {
      const existing = merged.get(account) ?? new Set<string>();
      const next = new Set<string>(existing);
      for (const id of ids) next.add(id);
      merged.set(account, next);
    }
    const result = evaluateGates(samples, merged);
    expect(result.passed).toBe(false);
    if (!result.passed) {
      const text = result.reasons.join("\n");
      expect(text).toMatch(/foreign|revoked/);
    }
  });

  test("a correct in-memory provider passes both gates", async () => {
    const { buildSyntheticCorpus } = await import("../src/corpus");
    const { runWorkload } = await import("../src/harness");
    const { createVectorizeProvider } = await import(
      "../src/providers/vectorize"
    );
    const corpus = buildSyntheticCorpus();
    const provider = createVectorizeProvider();
    const { samples } = await runWorkload(provider, corpus, {
      k: 5,
      deleteCount: 2,
    });
    const merged = new Map<string, ReadonlySet<string>>();
    for (const doc of corpus.docs) {
      const existing = merged.get(doc.accountId) ?? new Set<string>();
      const next = new Set<string>(existing);
      next.add(doc.id);
      merged.set(doc.accountId, next);
    }
    const result = evaluateGates(samples, merged);
    expect(result.passed).toBe(true);
  });
});
