import { describe, expect, test } from "bun:test";

import { runChatGenerationScenario } from "./generation-scenario";
import { readChatGenerationSourceCapability } from "./generation-source";

describe("deterministic Chat generation scenarios", () => {
  test("canonicalizes untrusted tier declarations without claiming provider proof", () => {
    const mutable = {
      tier: "real-provider" as const,
      adapter: "local-provider",
      deterministic: false,
    };
    const detached = readChatGenerationSourceCapability({
      capability: mutable,
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    mutable.adapter = "mutated";
    expect(detached).toEqual({ tier: "real-provider", adapter: "local-provider", deterministic: false });
    expect(Object.isFrozen(detached)).toBe(true);
    expect(readChatGenerationSourceCapability({
      capability: ({
        tier: "real-provider", adapter: "local-provider", deterministic: false, extra: true,
      } as unknown as { tier: "real-provider"; adapter: string; deterministic: boolean }),
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    expect(readChatGenerationSourceCapability({
      capability: Object.create({ tier: "real-provider", adapter: "local-provider", deterministic: false }),
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    expect(readChatGenerationSourceCapability({
      capability: { tier: "real-provider", adapter: "", deterministic: false },
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    expect(readChatGenerationSourceCapability({
      capability: { tier: "real-provider", adapter: "x".repeat(129), deterministic: false },
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    expect(readChatGenerationSourceCapability({
      capability: { tier: "real-provider", adapter: "local-provider", deterministic: true },
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    expect(readChatGenerationSourceCapability({
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    expect(readChatGenerationSourceCapability({
      capability: { tier: "real-provider", adapter: "local-provider", deterministic: false },
      start: () => Object.freeze({ cancel: (): void => {} }),
    })).toEqual({ tier: "real-provider", adapter: "local-provider", deterministic: false });
  });

  test("records prompt deltas and completion with a scripted capability receipt", async () => {
    const result = await runChatGenerationScenario({
      prompt: "hello",
      script: [
        { delayMs: 5, text: "hi " },
        { delayMs: 7, text: "there" },
      ],
    });
    expect(result.capability).toEqual({
      tier: "deterministic-scripted",
      adapter: "scripted-chat-generation",
      deterministic: true,
    });
    expect(result.trace).toEqual([
      { atMs: 0, kind: "snapshot", text: "" },
      { atMs: 5, kind: "delta", text: "hi " },
      { atMs: 12, kind: "delta", text: "there" },
      { atMs: 12, kind: "done" },
    ]);
    expect(result.terminal).toBe("done");
  });

  test("provider and context faults are truthful failed terminals", async () => {
    const provider = await runChatGenerationScenario({
      prompt: "provider",
      script: [{ delayMs: 5, text: "partial" }],
      sourceErrorAtMs: 4,
    });
    const context = await runChatGenerationScenario({ prompt: "context", contextError: true });
    const attachment = await runChatGenerationScenario({ prompt: "attachment", attachmentError: true });
    expect(provider.trace.at(-1)).toEqual({
      atMs: 4,
      kind: "failed",
      errorCode: "generation_provider_failed",
    });
    expect(context.trace.at(-1)).toEqual({
      atMs: 0,
      kind: "failed",
      errorCode: "generation_context_failed",
    });
    expect(attachment.trace.at(-1)).toEqual({
      atMs: 0,
      kind: "failed",
      errorCode: "generation_attachment_failed",
    });
    expect(provider.terminal).toBe("failed");
    expect(context.terminal).toBe("failed");
    expect(attachment.terminal).toBe("failed");
    expect(provider.trace.filter((entry) => ["done", "failed", "cancelled"].includes(entry.kind)))
      .toHaveLength(1);
  });

  test("callback faults, cancellation, and timeout each have one terminal", async () => {
    const callback = await runChatGenerationScenario({
      prompt: "callback",
      script: [{ delayMs: 2, text: "ignored" }],
      callbackFault: "delta",
    });
    const cancelled = await runChatGenerationScenario({
      prompt: "cancel",
      script: [{ delayMs: 5, text: "late" }],
      cancelAtMs: 1,
    });
    const timeout = await runChatGenerationScenario({
      prompt: "timeout",
      script: [{ delayMs: 5, text: "late" }],
      timeoutAtMs: 1,
    });
    for (const result of [callback, cancelled, timeout]) {
      expect(result.trace.filter((entry) => ["done", "failed", "cancelled"].includes(entry.kind)))
        .toHaveLength(1);
    }
    expect(callback.terminal).toBe("failed");
    expect(cancelled.terminal).toBe("cancelled");
    expect(timeout.terminal).toBe("failed");
    expect(timeout.trace.at(-1)).toEqual({
      atMs: 1,
      kind: "failed",
      errorCode: "generation_timeout",
    });
  });

  test("the same declarative scenario produces an identical durable trace", async () => {
    const scenario = {
      generationId: "stable",
      prompt: "stable",
      context: ["one"],
      script: [
        { delayMs: 3, text: "a" },
        { delayMs: 4, text: "b" },
      ],
    } as const;
    const first = await runChatGenerationScenario(scenario);
    const second = await runChatGenerationScenario(scenario);
    expect(second).toEqual(first);
  });
});
