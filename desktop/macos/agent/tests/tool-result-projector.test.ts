import { describe, expect, it } from "vitest";

import { toolManifestEntry } from "../src/runtime/omi-tool-manifest.js";
import {
  projectToolResultPayload,
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

  it("keeps realistic recap content and exact per-record counts", () => {
    const conversations = Array.from({ length: 52 }, (_, index) => ({
      title: `Conversation ${index + 1}`,
      summary: `Met person ${index + 1} and discussed ${"a detailed topic ".repeat(10 + (index % 8))}`,
      createdAt: `2026-08-31T${String(23 - (index % 23)).padStart(2, "0")}:00:00Z`,
    }));
    const sections = [
      { name: "summary", total: 1, items: [{ title: "Yesterday recap" }] },
      { name: "apps", total: 11, items: Array.from({ length: 11 }, (_, i) => ({ title: `App ${i}`, minutes: 30 + i })) },
      { name: "conversations", total: 52, items: conversations },
      { name: "tasks", total: 3, items: Array.from({ length: 3 }, (_, i) => ({ title: `Task ${i}` })) },
      { name: "focus", total: 4, items: Array.from({ length: 4 }, (_, i) => ({ title: `Focus ${i}` })) },
      { name: "memories", total: 36, items: Array.from({ length: 36 }, (_, i) => ({ title: `Memory ${i}`, summary: "remembered detail ".repeat(8) })) },
      { name: "observations", total: 10, items: Array.from({ length: 10 }, (_, i) => ({ title: `Observation ${i}` })) },
    ];
    const projected = projectToolResultPayload({
      toolName: "get_daily_recap",
      result: JSON.stringify({ ok: true, sections }),
      maxBytes: 7_424,
    });
    expect(Buffer.byteLength(JSON.stringify(projected), "utf8")).toBeLessThanOrEqual(7_424);
    expect(52 - projected.omitted.conversations).toBeGreaterThanOrEqual(5);
    for (const section of sections) {
      const shown = section.total - projected.omitted[section.name];
      expect(shown).toBeGreaterThanOrEqual(1);
      expect(shown + projected.omitted[section.name]).toBe(section.total);
    }
    expect(conversations.filter((item) => projected.text.includes(item.title)).length).toBeGreaterThanOrEqual(5);
  });

  it("bounds transcript-bearing search items without dropping their titles", () => {
    const conversations = Array.from({ length: 12 }, (_, index) => ({
      title: `Search conversation ${index + 1}`,
      summary: `Relevant summary ${index + 1}`,
      transcript: `Speaker: ${"long transcript evidence ".repeat(180)}`,
      createdAt: `2026-08-${String(31 - index).padStart(2, "0")}T12:00:00Z`,
    }));
    const projected = projectToolResultPayload({
      toolName: "search_conversations",
      result: JSON.stringify({ sections: [{ name: "conversations", total: 12, items: conversations }] }),
      maxBytes: 7_424,
    });
    expect(Buffer.byteLength(JSON.stringify(projected), "utf8")).toBeLessThanOrEqual(7_424);
    expect(12 - projected.omitted.conversations).toBeGreaterThanOrEqual(5);
    expect(conversations.filter((item) => projected.text.includes(item.title)).length).toBeGreaterThanOrEqual(5);
  });

});
