import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  construct: vi.fn(),
  get: vi.fn(),
  set: vi.fn(),
  del: vi.fn(),
  on: vi.fn(),
}));
vi.mock("ioredis", () => ({
  default: class {
    constructor(options: unknown) {
      mocks.construct(options);
    }
    get = mocks.get;
    set = mocks.set;
    del = mocks.del;
    on = mocks.on;
  },
}));
beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.unstubAllEnvs();
  vi.stubEnv("REDIS_HOST", "test-redis");
});
describe("shared admin Redis accessor", () => {
  it("exports the same lazy client existing helpers use", async () => {
    const cache = await import("@/lib/redis");
    const first = cache.getRedis();
    expect(cache.getRedis()).toBe(first);
    mocks.get.mockResolvedValue('{"value":1}');
    expect(await cache.getJsonCache("key")).toEqual({ value: 1 });
    await cache.setJsonCache("key", { value: 2 }, 60);
    await cache.invalidateEnforcementCache("u");
    expect(mocks.construct).toHaveBeenCalledTimes(1);
    const options = mocks.construct.mock.calls[0][0];
    expect(options.connectTimeout).toBe(100);
    expect(options.commandTimeout).toBe(100);
    expect(options.maxRetriesPerRequest).toBe(0);
    expect(options.autoResendUnfulfilledCommands).toBe(false);
    expect(mocks.set).toHaveBeenCalledWith("key", '{"value":2}', "EX", 60);
    expect(mocks.del).toHaveBeenCalledWith("fair_use:stage:u");
  });
  it("returns null without Redis configuration", async () => {
    vi.stubEnv("REDIS_HOST", "");
    const cache = await import("@/lib/redis");
    expect(cache.getRedis()).toBeNull();
    expect(await cache.getJsonCache("key")).toBeNull();
    expect(mocks.construct).not.toHaveBeenCalled();
  });
});
