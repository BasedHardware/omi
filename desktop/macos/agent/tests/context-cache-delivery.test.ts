import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { recordJournalTurn } from "../src/runtime/conversation-journal.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import { createKernelHarness } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("pi-mono context cache delivery", () => {
  it("hydrates a binding once and sends later history as a delta", async () => {
    const root = mkdtempSync(join(tmpdir(), "omi-context-cache-"));
    roots.push(root);
    const { store, adapter, kernel } = createKernelHarness(
      join(root, "agent.sqlite"),
      "pi-mono",
      1,
    );
    const surface = resolveSurfaceSession(store, {
      ownerId: "owner-cache",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "pi-mono",
    }, () => 1);
    for (let sequence = 1; sequence <= 64; sequence += 1) {
      recordJournalTurn(store, {
        ownerId: "owner-cache",
        conversationId: surface.conversationId,
        turnId: `cache-turn-${sequence}`,
        role: sequence % 2 ? "user" : "assistant",
        surfaceKind: "main_chat",
        origin: "typed_chat",
        status: "completed",
        content: `cache canonical turn ${sequence}`,
        contentBlocks: [],
        createdAtMs: sequence,
      });
    }

    const common = {
      sessionId: surface.agentSessionId,
      ownerId: "owner-cache",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      defaultAdapterId: "pi-mono",
      adapterId: "pi-mono",
      clientId: "cache-test",
      cwd: root,
    } as const;
    await kernel.executeRun({ ...common, requestId: "cache-request-1", prompt: "first question" });

    recordJournalTurn(store, {
      ownerId: "owner-cache",
      conversationId: surface.conversationId,
      turnId: "cache-turn-65",
      role: "user",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "cache canonical turn 65",
      contentBlocks: [],
      createdAtMs: 65,
    });
    await kernel.executeRun({ ...common, requestId: "cache-request-2", prompt: "second question" });

    expect(adapter.executed).toHaveLength(2);
    const firstPrompt = adapter.executed[0].prompt
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    const secondPrompt = adapter.executed[1].prompt
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    expect(firstPrompt).toContain("cache canonical turn 1");
    expect(firstPrompt).toContain("cache canonical turn 64");
    expect(secondPrompt).toContain("delivery=delta");
    expect(secondPrompt).toContain("cache canonical turn 65");
    expect(secondPrompt).not.toContain("cache canonical turn 2");
    expect(secondPrompt).toContain("# User Message\nsecond question");
    store.close();
  });
});
