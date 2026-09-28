import { describe, expect, test } from "bun:test";

import { validateCorpus } from "../src/fixtures";

const validDoc = {
  id: "doc-alpha-001",
  accountId: "acct-synthetic-alpha",
  embedding: [1, 0, 0],
  terms: ["alpha", "vector"],
  revoked: false,
  synthetic: true,
} as const;

const validQuery = {
  id: "query-alpha-001",
  accountId: "acct-synthetic-alpha",
  embedding: [1, 0, 0],
  terms: ["alpha"],
  relevantDocIds: ["doc-alpha-001"],
} as const;

describe("fixture validator", () => {
  test("accepts a clean synthetic corpus", () => {
    const result = validateCorpus([validDoc], [validQuery]);
    expect(result.ok).toBe(true);
  });

  test("rejects a doc whose synthetic flag is not literally true", () => {
    const result = validateCorpus(
      [{ ...validDoc, synthetic: false }],
      [validQuery]
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons.join("\n")).toContain("synthetic");
    }
  });

  test("rejects a doc missing the synthetic flag", () => {
    const { synthetic: _removed, ...doc } = validDoc;
    void _removed;
    const result = validateCorpus([doc], [validQuery]);
    expect(result.ok).toBe(false);
  });

  test("rejects a doc carrying a production-like field (email)", () => {
    const result = validateCorpus(
      [{ ...validDoc, email: "real@user.example" }],
      [validQuery]
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons.join("\n")).toContain("email");
    }
  });

  test("rejects a doc carrying a production-like field (transcript)", () => {
    const result = validateCorpus(
      [{ ...validDoc, transcript: "hi, here is my card number" }],
      [validQuery]
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons.join("\n")).toContain("transcript");
    }
  });

  test("rejects an accountId that is not a synthetic scope", () => {
    const result = validateCorpus(
      [{ ...validDoc, accountId: "acct-prod-7f3a" }],
      [{ ...validQuery, accountId: "acct-prod-7f3a" }]
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons.join("\n")).toContain("accountId");
    }
  });

  test("rejects a query with an unresolved relevance id", () => {
    const result = validateCorpus(
      [validDoc],
      [{ ...validQuery, relevantDocIds: ["doc-does-not-exist"] }]
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons.join("\n")).toContain("unresolved");
    }
  });

  test("rejects a query whose relevance id resolves to a foreign account", () => {
    const result = validateCorpus(
      [validDoc],
      [
        {
          ...validQuery,
          accountId: "acct-synthetic-beta",
          relevantDocIds: ["doc-alpha-001"],
        },
      ]
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons.join("\n")).toContain("foreign");
    }
  });
});
