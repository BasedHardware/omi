import { createServer, type Socket } from "node:net";
import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ update: vi.fn() }));
vi.mock("@/lib/firebase/admin", () => ({
  default: { firestore: { FieldValue: { delete: () => "DELETE" } } },
  getDb: () => ({
    collection: () => ({ doc: () => ({ update: mocks.update }) }),
  }),
}));

afterEach(() => vi.unstubAllEnvs());

it("bounds real Redis blackholes and still writes without a backend lever", async () => {
  vi.resetModules();
  const sockets = new Set<Socket>();
  const server = createServer((socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
    // Accept TCP and consume bytes, but never reply to Redis.
    socket.on("data", () => {});
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("missing TCP address");
  vi.stubEnv("REDIS_HOST", "127.0.0.1");
  vi.stubEnv("REDIS_PORT", String(address.port));
  vi.stubEnv("REDIS_PASSWORD", "");
  vi.stubEnv("FIRESTORE_READ_LEVERS", "");
  const { getRedis } = await import("@/lib/redis");
  const { updateSingleUserSubscription } = await import(
    "@/lib/utils/user-subscription"
  );
  const client = getRedis();
  try {
    const started = performance.now();
    await updateSingleUserSubscription("u", {
      plan: "operator",
      status: "active",
    });
    expect(performance.now() - started).toBeLessThan(1500);
    expect(mocks.update).toHaveBeenCalledOnce();
    expect(getRedis()).toBe(client);
  } finally {
    client?.disconnect();
    sockets.forEach((socket) => socket.destroy());
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
