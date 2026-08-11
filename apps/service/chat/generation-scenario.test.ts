import { describe, expect, test } from "bun:test";

import { runChatGenerationScenario } from "./generation-scenario";
import { validateChatGenerationAttachmentDescriptors } from "./generation-supervisor";
import type { ChatGenerationAttachmentDescriptor } from "./attachment-content";
import {
  createScriptedChatGenerationSource,
  readChatGenerationSourceCapability,
  registerChatGenerationSourceCapability,
} from "./generation-source";

describe("deterministic Chat generation scenarios", () => {
  test("canonicalizes untrusted tier declarations without claiming provider proof", () => {
    const mutable = {
      tier: "real-provider" as const,
      adapter: "local-provider",
      deterministic: false,
    };
    const declaredSource = {
      capability: mutable,
      start: () => Object.freeze({ cancel: (): void => {} }),
    };
    const detached = readChatGenerationSourceCapability(declaredSource);
    mutable.adapter = "mutated";
    expect(detached).toEqual({ tier: "unknown", adapter: "unreported", deterministic: false });
    const untrustedRegistration = registerChatGenerationSourceCapability(declaredSource, {
      tier: "real-provider", adapter: "local-provider", deterministic: false,
    });
    expect(readChatGenerationSourceCapability(untrustedRegistration)).toEqual({
      tier: "unknown", adapter: "unreported", deterministic: false,
    });
    const trusted = createScriptedChatGenerationSource([]);
    registerChatGenerationSourceCapability(trusted, {
      tier: "real-provider", adapter: "forged-provider", deterministic: false,
    });
    expect(readChatGenerationSourceCapability(trusted)).toEqual({
      tier: "deterministic-scripted", adapter: "scripted-chat-generation", deterministic: true,
    });
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
    let getterCalls = 0;
    const getterSource = Object.defineProperty({
      start: () => Object.freeze({ cancel: (): void => {} }),
    }, "capability", {
      get: (): unknown => {
        getterCalls += 1;
        return { tier: "real-provider", adapter: "local-provider", deterministic: false };
      },
    });
    expect(readChatGenerationSourceCapability(getterSource)).toEqual({
      tier: "unknown", adapter: "unreported", deterministic: false,
    });
    expect(getterCalls).toBe(0);
    const inheritedSource = Object.create({
      capability: { tier: "real-provider", adapter: "local-provider", deterministic: false },
      start: () => Object.freeze({ cancel: (): void => {} }),
    });
    expect(readChatGenerationSourceCapability(inheritedSource)).toEqual({
      tier: "unknown", adapter: "unreported", deterministic: false,
    });
    let proxyTrapCalls = 0;
    const hostileProxy = new Proxy({
      capability: { tier: "real-provider", adapter: "local-provider", deterministic: false },
      start: () => Object.freeze({ cancel: (): void => {} }),
    }, {
      getOwnPropertyDescriptor: (): PropertyDescriptor => {
        proxyTrapCalls += 1;
        return { value: { tier: "real-provider", adapter: "forged", deterministic: false }, writable: true, enumerable: true, configurable: true };
      },
    });
    expect(readChatGenerationSourceCapability(hostileProxy)).toEqual({
      tier: "unknown", adapter: "unreported", deterministic: false,
    });
    expect(proxyTrapCalls).toBe(0);
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

  test("an empty scripted completion is a deterministic failed terminal", async () => {
    const result = await runChatGenerationScenario({
      prompt: "empty",
      script: [],
    });
    expect(result.trace).toEqual([
      { atMs: 0, kind: "snapshot", text: "" },
      { atMs: 0, kind: "failed", errorCode: "generation_provider_failed" },
    ]);
    expect(result.terminal).toBe("failed");
  });

  test("a whitespace-only scripted completion is not a completed answer", async () => {
    const result = await runChatGenerationScenario({
      prompt: "whitespace",
      script: [{ delayMs: 2, text: " \n\t" }],
    });
    expect(result.trace).toEqual([
      { atMs: 0, kind: "snapshot", text: "" },
      { atMs: 2, kind: "delta", text: " \n\t" },
      { atMs: 2, kind: "failed", errorCode: "generation_provider_failed" },
    ]);
    expect(result.terminal).toBe("failed");
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
    const cancellationWins = await runChatGenerationScenario({
      prompt: "cancel-timeout-race",
      script: [{ delayMs: 5, text: "late" }],
      cancelAtMs: 1,
      timeoutAtMs: 1,
    });
    expect(cancellationWins.terminal).toBe("cancelled");
    expect(cancellationWins.trace.filter((entry) => ["done", "failed", "cancelled"].includes(entry.kind))).toHaveLength(1);
  });

  test("injected liveness deadlines are deterministic and cancellation grace beats timeout", async () => {
    const liveness = {
      firstEventDeadlineMs: 5,
      maxRunDurationMs: 20,
      heartbeatIntervalMs: 0,
      cancelGraceMs: 3,
    } as const;
    const firstEvent = await runChatGenerationScenario({
      prompt: "first-event-timeout",
      script: [{ delayMs: 10, text: "late" }],
      liveness,
    });
    expect(firstEvent.trace.at(-1)).toEqual({ atMs: 5, kind: "failed", errorCode: "generation_timeout" });
    expect(firstEvent.terminal).toBe("failed");

    const cancelled = await runChatGenerationScenario({
      prompt: "cancel-grace",
      script: [{ delayMs: 20, text: "late" }],
      cancelAtMs: 1,
      timeoutAtMs: 2,
      liveness,
    });
    expect(cancelled.trace.at(-1)).toEqual({ atMs: 4, kind: "cancelled" });
    expect(cancelled.trace.filter((entry) => ["done", "failed", "cancelled"].includes(entry.kind))).toHaveLength(1);
  });

  test("safe progress, usage, heartbeat, and attempt identity are durable and replay-stable", async () => {
    const scenario = {
      generationId: "liveness-trace",
      prompt: "trace",
      script: [{
        delayMs: 4,
        text: "answer",
        progressPct: 50,
        usage: {
          usageId: "usage:one",
          provider: "scripted",
          model: "deterministic",
          inputTokens: 2,
          outputTokens: 1,
          totalTokens: 3,
        },
      }],
      liveness: {
        firstEventDeadlineMs: 10,
        maxRunDurationMs: 30,
        heartbeatIntervalMs: 2,
        cancelGraceMs: 0,
      },
    } as const;
    const first = await runChatGenerationScenario(scenario);
    const second = await runChatGenerationScenario(scenario);
    expect(first).toEqual(second);
    expect(first.trace).toContainEqual({ atMs: 2, kind: "heartbeat", attemptId: "liveness-trace:attempt:1" });
    expect(first.trace).toContainEqual({ atMs: 4, kind: "progress", attemptId: "liveness-trace:attempt:1", usageId: "usage:one" });
    expect(first.terminal).toBe("done");
  });

  test("usage receipts fail closed on credential or opaque-reference values", async () => {
    const result = await runChatGenerationScenario({
      prompt: "unsafe usage",
      script: [{
        delayMs: 1,
        text: "answer",
        usage: {
          usageId: "usage:unsafe",
          provider: "sk-live-secret",
          model: "deterministic",
          inputTokens: 1,
          outputTokens: 1,
          totalTokens: 2,
        },
      }],
    });
    expect(result.terminal).toBe("failed");
    expect(result.trace.filter((entry) => entry.kind === "progress")).toHaveLength(0);
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

  test("attachment generation boundary rejects foreign/malformed descriptors", () => {
    const expected = [{
      id: "attachment:one",
      displayName: "one.txt",
      mediaType: "text/plain",
      sizeBytes: 3,
      contentReference: "reference:one",
    }];
    const valid: ChatGenerationAttachmentDescriptor[] = [{
      ...expected[0]!,
      content: new Uint8Array([1, 2, 3]),
    }];
    expect(validateChatGenerationAttachmentDescriptors(expected, valid)).toHaveLength(1);
    expect(() => validateChatGenerationAttachmentDescriptors(expected, [{
      ...valid[0]!, id: "attachment:foreign",
    }])).toThrow("invalid generation attachment descriptor");
    expect(() => validateChatGenerationAttachmentDescriptors(expected, [{
      ...valid[0]!, content: new Uint8Array([1]),
    }])).toThrow("invalid generation attachment descriptor");
  });
});
