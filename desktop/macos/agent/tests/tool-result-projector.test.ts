import { describe, expect, it } from "vitest";

import { toolManifestEntry } from "../src/runtime/omi-tool-manifest.js";
import {
  projectionIsComplete,
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

  it("keeps manifest priority order when the contract does not opt into purpose ranking", () => {
    const raw = JSON.stringify({ sections: [{
      name: "results",
      total: 2,
      items: ["routine planning", "Met Ada Lovelace at the compiler meetup"],
    }] });
    const result = projectToolResultPayload({
      toolName: "capture_screen",
      result: raw,
      purpose: "interesting person Ada",
      purposeRankingEnabled: true,
      maxBytes: 300,
    });
    expect(result.text.indexOf("routine planning")).toBeLessThan(result.text.indexOf("Ada Lovelace"));
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

  it("renders recap scalar fields and marks only actually excerpted items incomplete", () => {
    const complete = projectToolResultPayload({
      toolName: "get_daily_recap",
      result: JSON.stringify({ sections: [
        {
          name: "apps",
          total: 1,
          items: [{ title: "Omi", minutes: 45.5, captures: 12, firstSeenAt: "09:00", lastSeenAt: "17:30" }],
        },
        {
          name: "tasks",
          total: 1,
          items: [{ title: "Ship round five", completed: false, priority: "high" }],
        },
      ] }),
      maxBytes: 6_656,
    });
    expect(complete.text).toContain("minutes=45.5");
    expect(complete.text).toContain("captures=12");
    expect(complete.text).toContain("priority=high");
    expect(projectionIsComplete(complete)).toBe(true);

    const excerpted = projectToolResultPayload({
      toolName: "search_conversations",
      result: JSON.stringify({ sections: [{
        name: "conversations",
        total: 1,
        items: [{ title: "Kept title", summary: "Kept summary", content: "transcript ".repeat(500) }],
      }] }),
      maxBytes: 700,
    });
    expect(excerpted.text).toContain("title: Kept title");
    expect(excerpted.text).toContain("content:");
    expect(projectionIsComplete(excerpted)).toBe(false);
  });

  it("bounds transcript-bearing search items without dropping their titles", () => {
    // Literal fixture matches JSONSerialization(.sortedKeys) output from
    // typedReadToolResult: content sorts before sourceId/summary/title.
    const conversations = Array.from({ length: 12 }, (_, index) => ({
      appName: "Omi",
      citationMarker: `[${index + 1}]`,
      content: `Speaker: ${"long transcript evidence ".repeat(180)}`,
      createdAt: `2026-08-${String(31 - index).padStart(2, "0")}T12:00:00Z`,
      sourceId: `conversation-${index + 1}`,
      summary: `Relevant summary ${index + 1}`,
      title: `Search conversation ${index + 1}`,
    }));
    const projected = projectToolResultPayload({
      toolName: "search_conversations",
      result: JSON.stringify({ sections: [{ name: "conversations", total: 12, items: conversations }] }),
      maxBytes: 7_424,
    });
    expect(Buffer.byteLength(JSON.stringify(projected), "utf8")).toBeLessThanOrEqual(7_424);
    expect(12 - projected.omitted.conversations).toBeGreaterThanOrEqual(5);
    expect(conversations.filter((item) => projected.text.includes(item.title)).length).toBeGreaterThanOrEqual(5);
    expect(conversations.filter((item) => projected.text.includes(item.summary)).length).toBeGreaterThanOrEqual(5);
    expect(projected.text).toContain("long transcript evidence");
  });

  it("marks unknown typed-result siblings omitted instead of silently dropping them", () => {
    const projected = projectToolResultPayload({
      toolName: "get_conversations",
      result: JSON.stringify({
        ok: true,
        transportPadding: "p".repeat(4_000),
        sections: [{ name: "conversations", total: 1, items: [{ title: "Planning", summary: "Release" }] }],
      }),
      maxBytes: 1_024,
    });
    expect(projected.text).toContain("meta (1 total)");
    expect(projected.omitted.meta).toBeDefined();
  });

  it("projects non-string reserved fields as meta and accounts for their truncation", () => {
    const projected = projectToolResultPayload({
      toolName: "get_daily_recap",
      result: JSON.stringify({
        ok: true,
        content: { transcript: "Y".repeat(5_000) },
        title: 42,
        sections: [{ name: "summary", total: 1, items: [{ title: "Yesterday" }] }],
      }),
      maxBytes: 1_024,
    });

    expect(projected.text).toContain("meta (1 total)");
    expect(projected.text).toContain("transcript");
    expect(projected.text).toContain("Y");
    expect(projectionIsComplete(projected)).toBe(false);
  });

});
