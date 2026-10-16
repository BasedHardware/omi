import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  updateUserSubscriptionDetails,
  removeUserSubscriptionDetails,
  updateSingleUserSubscription,
} from "@/lib/utils/user-subscription";
const mocks = vi.hoisted(() => ({
  events: [] as string[],
  eval: vi.fn(),
  getRedis: vi.fn(),
  commit: vi.fn(),
  update: vi.fn(),
  batchUpdate: vi.fn(),
}));
vi.mock("@/lib/redis", () => ({ getRedis: mocks.getRedis }));
vi.mock("@/lib/firebase/admin", () => ({
  default: { firestore: { FieldValue: { delete: () => "DELETE" } } },
  getDb: () => ({
    batch: () => ({ update: mocks.batchUpdate, commit: mocks.commit }),
    collection: () => ({
      doc: (uid: string) => ({ uid, update: mocks.update }),
    }),
  }),
}));
const subscription = {
  plan: "operator",
  status: "active",
  customer_id: "customer",
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
  vi.stubEnv("FIRESTORE_READ_LEVERS", "");
  mocks.events.length = 0;
  mocks.getRedis.mockImplementation(() => ({ eval: mocks.eval }));
  mocks.eval.mockImplementation(async (script: string) => {
    mocks.events.push(script.includes("SADD") ? "begin" : "end");
    return 1;
  });
  mocks.commit.mockImplementation(async () => {
    mocks.events.push("write");
  });
  mocks.update.mockImplementation(async () => {
    mocks.events.push("write");
  });
});
afterEach(() => vi.useRealTimers());
describe("subscription writer cache fences", () => {
  it.each(["grant", "remove"])(
    "bounds all 500 hung Redis invalidations for %s to one deadline",
    async (operation) => {
      vi.useFakeTimers();
      mocks.eval.mockImplementation(() => new Promise(() => {}));
      const employees = Array.from({ length: 500 }, (_, i) => ({
        uid: `u-${i}`,
      }));
      let completed = false;
      const result = (
        operation === "grant"
          ? updateUserSubscriptionDetails(employees, subscription)
          : removeUserSubscriptionDetails(employees)
      ).then(() => {
        completed = true;
      });
      expect(mocks.eval).toHaveBeenCalledTimes(500);
      expect(mocks.commit).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(125);
      expect(mocks.commit).toHaveBeenCalledOnce();
      expect(mocks.eval).toHaveBeenCalledTimes(1000);
      await vi.advanceTimersByTimeAsync(125);
      await result;
      expect(completed).toBe(true);
      expect(vi.getTimerCount()).toBe(0);
      // The same tokens pair begin/end even when begin never acknowledges.
      for (let i = 0; i < 500; i++) {
        expect(mocks.eval.mock.calls[500 + i][4]).toBe(
          mocks.eval.mock.calls[i][4]
        );
      }
    }
  );
  it("matches Python JSON key escaping for Unicode UIDs", async () => {
    await updateSingleUserSubscription("é😀\x7f", subscription);
    expect(mocks.eval.mock.calls[0][2]).toBe(
      'fsr:s4:v2:["subscription_cache","\\u00e9\\ud83d\\ude00\\u007f"]:generation'
    );
  });

  it.each(["grant", "remove", "single"])(
    "fences %s around the durable write",
    async (operation) => {
      if (operation === "grant")
        await updateUserSubscriptionDetails([{ uid: "u" }], subscription);
      if (operation === "remove")
        await removeUserSubscriptionDetails([{ uid: "u" }]);
      if (operation === "single")
        await updateSingleUserSubscription("u", subscription);
      expect(mocks.events).toEqual(["begin", "write", "end"]);
      const [begin, end] = mocks.eval.mock.calls;
      const root = 'fsr:s4:v2:["subscription_cache","u"]';
      expect(begin.slice(1, 4)).toEqual([
        2,
        root + ":generation",
        root + ":writers",
      ]);
      expect(end.slice(1, 4)).toEqual(begin.slice(1, 4));
      expect(end[4]).toBe(begin[4]);
      expect(end[5]).not.toBe(begin[4]);
      expect(begin[5]).toBe(120);
      expect(end[6]).toBe(120);
    }
  );
  it("fences each employee once, excluding missing UIDs", async () => {
    await updateUserSubscriptionDetails(
      [{ uid: "a" }, {}, { uid: "b" }, { uid: "a" }],
      subscription
    );
    expect(mocks.events).toEqual(["begin", "begin", "write", "end", "end"]);
    expect(mocks.eval.mock.calls[0][4]).not.toBe(mocks.eval.mock.calls[1][4]);
  });
  it.each([
    "",
    "{}",
    "invalid",
    '{"subscription_cache":true}',
    '{"subscription_cache":101}',
  ])(
    "fences writes regardless of off/invalid backend lever %s",
    async (config) => {
      vi.stubEnv("FIRESTORE_READ_LEVERS", config);
      await updateSingleUserSubscription("u", subscription);
      expect(mocks.getRedis).toHaveBeenCalledOnce();
      expect(mocks.events).toEqual(["begin", "write", "end"]);
    }
  );
  it("fences every writer regardless of the backend percentage cohort", async () => {
    vi.stubEnv("FIRESTORE_READ_LEVERS", '{"subscription_cache":50}');
    const uids = Array.from({ length: 20 }, (_, i) => `user-${i}`);
    await updateUserSubscriptionDetails(
      uids.map((uid) => ({ uid })),
      subscription
    );
    const actual = mocks.eval.mock.calls
      .filter(([script]) => script.includes("SADD"))
      .map((call) => call[2]);
    expect(actual).toEqual(
      uids.map(
        (uid) =>
          "fsr:s4:v2:" +
          JSON.stringify(["subscription_cache", uid]) +
          ":generation"
      )
    );
  });
  it.each(["999999", "0", "-5", "invalid"])(
    "clamps generation TTL %s",
    async (ttl) => {
      vi.stubEnv("FSR_SUBSCRIPTION_TTL_SECONDS", ttl);
      await updateSingleUserSubscription("u", subscription);
      expect(mocks.eval.mock.calls[0][5]).toBe(
        ttl === "0" || ttl === "-5" ? 2 : 120
      );
    }
  );
  it("preserves writes and attempts both invalidations during Redis errors", async () => {
    mocks.eval.mockRejectedValue(new Error("unavailable"));
    await updateSingleUserSubscription("u", subscription);
    expect(mocks.eval).toHaveBeenCalledTimes(2);
    expect(mocks.update).toHaveBeenCalledTimes(1);
  });
  it.each(["missing", "constructor"])(
    "preserves writes with %s Redis",
    async (mode) => {
      mocks.getRedis.mockImplementation(() => {
        if (mode === "constructor") throw new Error("unavailable");
        return null;
      });
      await updateSingleUserSubscription("u", subscription);
      expect(mocks.update).toHaveBeenCalledTimes(1);
    }
  );
  it("cleans up on a failed Firestore commit and propagates the error", async () => {
    mocks.commit.mockImplementation(async () => {
      mocks.events.push("write");
      throw new Error("commit failed");
    });
    await expect(removeUserSubscriptionDetails([{ uid: "u" }])).rejects.toThrow(
      "commit failed"
    );
    expect(mocks.events).toEqual(["begin", "write", "end"]);
  });
});
