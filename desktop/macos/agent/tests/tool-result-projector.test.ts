import { describe, expect, it, vi } from "vitest";

import { toolManifestEntry } from "../src/runtime/omi-tool-manifest.js";
import {
  projectToolResultPayload,
  projectToolResultWithDigest,
  toolResultBudgetBytes,
} from "../src/runtime/tool-result-projector.js";

const scoped = [
  ["get_daily_recap", ["apps", "conversations", "tasks", "focus", "memories", "observations"]],
  ["get_conversations", ["conversations"]],
  ["search_conversations", ["conversations"]],
  ["get_memories", ["memories"]],
  ["search_memories", ["memories"]],
  ["get_action_items", ["action_items"]],
] as const;

describe("manifest-owned tool result projection", () => {
  it.each(scoped)("projects maximal %s fixtures under every surface budget with totals", (toolName, names) => {
    const sections = names.map((name) => ({
      name,
      total: name.includes("memor") ? 300 : 500,
      items: Array.from({ length: name.includes("memor") ? 300 : 500 }, (_, index) => ({
        title: `${name}-${index}`,
        summary: "detail ".repeat(80),
        createdAt: `2026-09-01T12:${String(index % 60).padStart(2, "0")}:00Z`,
      })),
    }));
    const raw = JSON.stringify({ ok: true, tool: toolName, sections });
    const contract = toolManifestEntry(toolName)?.resultContract;
    expect(contract).toBeDefined();
    for (const surface of ["desktop_chat", "realtime_voice", "onboarding", "task_chat"] as const) {
      const budget = toolResultBudgetBytes(toolName, surface);
      const result = projectToolResultPayload({ toolName, result: raw, maxBytes: budget - 768 });
      expect(Buffer.byteLength(JSON.stringify(result), "utf8")).toBeLessThanOrEqual(budget - 768);
      for (const section of sections) expect(result.omitted[section.name]).toBeDefined();
    }
  });

  it("ranks purpose matches first only when the flag-controlled input is enabled", () => {
    const raw = JSON.stringify({ sections: [{
      name: "conversations",
      total: 2,
      items: ["routine planning", "Met Ada Lovelace at the compiler meetup"],
    }] });
    const result = projectToolResultPayload({
      toolName: "get_conversations",
      result: raw,
      purpose: "interesting person Ada",
      purposeRankingEnabled: true,
      maxBytes: 300,
    });
    expect(result.text.indexOf("Ada Lovelace")).toBeLessThan(result.text.indexOf("routine planning"));
  });

  it("returns the ranked fallback when the flagged digest lane times out", async () => {
    vi.useFakeTimers();
    const fallback = { text: "ranked fallback", omitted: { conversations: 42 } };
    const promise = projectToolResultWithDigest({
      fallback,
      budgetBytes: 1024,
      timeoutMs: 25,
      enabled: true,
      digest: () => new Promise<string>(() => undefined),
    });
    await vi.advanceTimersByTimeAsync(25);
    await expect(promise).resolves.toEqual(fallback);
    vi.useRealTimers();
  });

});
