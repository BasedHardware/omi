import { describe, expect, it } from "vitest";

import { AgentResultSchema, parseAgentResult } from "../agent-result.mjs";

const validBlock = (obj) => "prose for the human\n```json\n" + JSON.stringify(obj) + "\n```";

describe("parseAgentResult", () => {
  it("parses a well-formed fenced json result", () => {
    const r = parseAgentResult(
      validBlock({
        answer: "Xcode dominated.",
        findings: [{ claim: "top app", evidence: "60/120" }],
        confidence: "high",
        data_found: true,
      }),
    );
    expect(r.ok).toBe(true);
    expect(r.value.answer).toBe("Xcode dominated.");
    expect(r.value.findings[0].evidence).toBe("60/120");
  });

  it("applies schema defaults for optional fields", () => {
    const r = parseAgentResult(validBlock({ answer: "just an answer" }));
    expect(r.ok).toBe(true);
    expect(r.value.findings).toEqual([]);
    expect(r.value.confidence).toBe("medium");
    expect(r.value.data_found).toBe(true);
  });

  it("takes the LAST json block so an echoed example is ignored", () => {
    const text =
      "Here is the format:\n```json\n{\"answer\":\"EXAMPLE\"}\n```\n" +
      "and my real result:\n```json\n{\"answer\":\"REAL\"}\n```";
    const r = parseAgentResult(text);
    expect(r.ok).toBe(true);
    expect(r.value.answer).toBe("REAL");
  });

  it("parses a bare trailing object with no fence", () => {
    const r = parseAgentResult('some notes {"answer":"bare object works"}');
    expect(r.ok).toBe(true);
    expect(r.value.answer).toBe("bare object works");
  });

  // Reliability: every malformed shape degrades to prose fallback, never throws.
  it.each([
    ["empty string", ""],
    ["non-string", null],
    ["prose only, no json", "I could not find any structured data to report."],
    ["invalid json in fence", "```json\n{answer: not valid}\n```"],
    ["valid json, wrong shape (missing answer)", validBlock({ findings: [] })],
    ["valid json, answer empty", validBlock({ answer: "" })],
    ["valid json, findings wrong type", validBlock({ answer: "x", findings: "nope" })],
    ["bad confidence enum", validBlock({ answer: "x", confidence: "certain" })],
  ])("falls back to prose on %s (never throws)", (_label, input) => {
    const r = parseAgentResult(input);
    expect(r.ok).toBe(false);
    expect(typeof r.fallbackText).toBe("string");
  });

  it("preserves the prose as fallbackText when parsing fails", () => {
    const r = parseAgentResult("no json here, just words");
    expect(r).toEqual({ ok: false, fallbackText: "no json here, just words" });
  });

  it("schema is exported and self-consistent", () => {
    expect(AgentResultSchema.safeParse({ answer: "ok" }).success).toBe(true);
    expect(AgentResultSchema.safeParse({}).success).toBe(false);
  });
});
