import { env } from "cloudflare:workers";
import { runDurableObjectAlarm, runInDurableObject } from "cloudflare:test";
import { describe, expect, test } from "vitest";

const create = (id: string) => ({
  op: "create" as const,
  opId: `op-${id}`,
  id,
  at: 1,
  text: "hello",
  sender: "human" as const,
  journalRevision: 0,
  appId: null,
  chatSessionId: null,
  attachmentIds: [],
});

describe("AccountBackend persistence", () => {
  test("configuration updates identity and limits without resetting usage", async () => {
    const stub = env.ACCOUNTS.getByName(crypto.randomUUID());
    await stub.configure({
      displayName: "Before",
      email: "before@example.invalid",
      planLabel: "Original",
      chatLimit: 2,
    });
    const first = await stub.admit(create("first"));
    expect(typeof first).not.toBe("string");
    if (typeof first === "string") throw new Error("first admission refused");
    expect(first.created).toBe(true);

    await stub.configure({
      displayName: "After",
      email: "after@example.invalid",
      planLabel: "Reduced",
      chatLimit: 1,
    });

    expect(await stub.settings()).toEqual({
      identity: {
        displayName: "After",
        email: "after@example.invalid",
      },
      entitlement: {
        planLabel: "Reduced",
        limitKey: "chat",
        used: 1,
        limit: 1,
        limitReached: true,
        upgradeAvailable: true,
      },
    });
    expect(await stub.admit(create("second"))).toBe("entitlement");
  });

  test("admission persists canonical state and schedules recoverable generation work", async () => {
    const stub = env.ACCOUNTS.getByName(crypto.randomUUID());
    await stub.configure({
      displayName: "Account",
      email: "account@example.invalid",
      planLabel: "Metered",
      chatLimit: 1,
    });

    const admission = await stub.admit(create("message"));
    if (typeof admission === "string") throw new Error("admission refused");
    expect(admission.created).toBe(true);
    const history = await stub.history(50);
    if (history === "invalid_cursor")
      throw new Error("history cursor rejected");
    expect(history.messages).toEqual([admission.message]);
    expect(
      await runInDurableObject(stub, (_instance, state) =>
        state.storage.getAlarm()
      )
    ).not.toBeNull();
    const replay = await stub.admit(create("message"));
    if (typeof replay === "string") throw new Error("replay refused");
    expect(replay.created).toBe(false);
    expect((await stub.settings()).entitlement?.used).toBe(1);
  });

  test("provider failure terminates its generation and advances queued work", async () => {
    const stub = env.ACCOUNTS.getByName(crypto.randomUUID());
    await stub.configure({
      displayName: "Account",
      email: "account@example.invalid",
      planLabel: "Metered",
      chatLimit: 2,
    });
    const first = await stub.admit(create("first"));
    const second = await stub.admit(create("second"));
    if (typeof first === "string" || typeof second === "string")
      throw new Error("admission refused");

    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          AI_MODEL: "test-model",
          AI: {
            run: async () => {
              throw new Error("provider unavailable");
            },
          },
        },
      });
    });
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    const failed = await stub.fetch(
      `https://account.internal/events?generationId=${first.generation.id}`
    );
    expect(await failed.text()).toContain("event: failed");
    expect(
      await runInDurableObject(stub, (_instance, state) =>
        state.storage.getAlarm()
      )
    ).not.toBeNull();

    await runInDurableObject(stub, (instance) => {
      Object.defineProperty(instance, "env", {
        configurable: true,
        value: {
          AI_MODEL: "test-model",
          AI: { run: async () => ({ response: "second completed" }) },
        },
      });
    });
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    const completed = await stub.fetch(
      `https://account.internal/events?generationId=${second.generation.id}`
    );
    expect(await completed.text()).toContain("event: done");
    const history = await stub.history(50);
    if (history === "invalid_cursor")
      throw new Error("history cursor rejected");
    expect(history.messages.map((message) => message.text)).toEqual([
      "hello",
      "hello",
      "second completed",
    ]);
  });
});
