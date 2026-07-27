import { describe, expect, it } from "vitest";

import {
  appendArchive,
  buildCondensedSeed,
  estimateChars,
  planCondensation,
  searchArchive,
} from "../conversation-condenser.mjs";

const turn = (u, a) => ({ user: u, assistant: a });
const big = (n) => "x".repeat(n);

describe("planCondensation", () => {
  it("does not condense under the char budget", () => {
    const turns = [turn("hi", "hello"), turn("how are you", "good")];
    expect(planCondensation(turns, { maxChars: 60000 }).condense).toBe(false);
  });

  it("does not condense when everything is within keepRecent (nothing old to fold)", () => {
    const turns = [turn(big(40000), big(40000)), turn(big(40000), big(40000))];
    // over budget, but only 2 turns and keepRecent=4 → nothing old enough
    expect(planCondensation(turns, { maxChars: 60000, keepRecent: 4 }).condense).toBe(false);
  });

  it("condenses old turns while keeping recent ones verbatim", () => {
    const turns = [];
    for (let i = 0; i < 10; i++) turns.push(turn(`q${i} ${big(8000)}`, `a${i}`));
    const plan = planCondensation(turns, { maxChars: 60000, keepRecent: 3 });
    expect(plan.condense).toBe(true);
    expect(plan.keep).toHaveLength(3);
    expect(plan.summarize).toHaveLength(7);
    // the kept turns are the LAST three, verbatim
    expect(plan.keep.map((t) => t.user.slice(0, 2))).toEqual(["q7", "q8", "q9"]);
    // archive == the summarized turns (non-destructive: nothing dropped)
    expect(plan.archive).toEqual(plan.summarize);
  });

  it("estimateChars counts both sides", () => {
    expect(estimateChars([turn("abcd", "efgh")])).toBe(8);
  });
});

describe("buildCondensedSeed", () => {
  it("puts the summary first, then recent turns verbatim, and flags the archive", () => {
    const seed = buildCondensedSeed("SUMMARY_TEXT", [turn("recent q", "recent a")]);
    expect(seed).toContain("SUMMARY_TEXT");
    expect(seed).toContain("User: recent q");
    expect(seed).toContain("Assistant: recent a");
    expect(seed.toLowerCase()).toContain("archived and retrievable");
    // recent turn appears verbatim, not summarized
    expect(seed.indexOf("SUMMARY_TEXT")).toBeLessThan(seed.indexOf("recent q"));
  });
});

describe("archive (non-destructive)", () => {
  it("appendArchive accumulates without mutating input", () => {
    const a = [turn("old", "x")];
    const b = appendArchive(a, [turn("older", "y")]);
    expect(a).toHaveLength(1); // unchanged
    expect(b).toHaveLength(2);
  });

  it("searchArchive retrieves raw turns by substring — the escape hatch", () => {
    const archive = [
      turn("my allergy is shellfish", "noted"),
      turn("what time is it", "3pm"),
      turn("remind me about the dentist", "ok"),
    ];
    const hits = searchArchive(archive, "shellfish");
    expect(hits).toHaveLength(1);
    expect(hits[0].user).toContain("shellfish");
    expect(searchArchive(archive, "nonexistent")).toEqual([]);
  });
});
