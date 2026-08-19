import { expect, test } from "bun:test";
import {
  createWebNativeAdapter,
  omiBackend,
  omiNative,
} from "../../react-native/src/omiNative.web";

test("web backend uses the origin-relative proxy without browser credentials", async () => {
  const calls: Array<{
    credentials: RequestCredentials | undefined;
    headers: Headers;
    input: RequestInfo | URL;
  }> = [];
  const previousFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    calls.push({
      credentials: init?.credentials,
      headers: new Headers(init?.headers),
      input,
    });
    return new Response('{"ok":true}', { status: 200 });
  }) as typeof globalThis.fetch;

  try {
    await expect(
      omiBackend.request({
        id: "settings",
        method: "GET",
        path: "/v1/settings",
      })
    ).resolves.toEqual(
      expect.objectContaining({ id: "settings", status: 200 })
    );
    await expect(
      omiBackend.request({
        headers: { authorization: "Bearer secret" },
        id: "credentialed",
        method: "GET",
        path: "/v1/settings",
      })
    ).rejects.toThrow("authorization");
  } finally {
    globalThis.fetch = previousFetch;
  }

  expect(calls).toHaveLength(1);
  expect(calls[0]).toEqual(
    expect.objectContaining({
      credentials: "omit",
      input: "/__omi/api/v1/settings",
    })
  );
  expect(calls[0]?.headers.get("authorization")).toBeNull();
});

test("web backend uses the native JSON body policy without browser credentials", async () => {
  const calls: RequestInit[] = [];
  const previousFetch = globalThis.fetch;
  globalThis.fetch = (async (_input, init) => {
    calls.push(init ?? {});
    return new Response('{"ok":true}', { status: 200 });
  }) as typeof globalThis.fetch;

  try {
    await omiBackend.request({
      body: '{"text":"hello"}',
      headers: { "content-type": "text/plain" },
      id: "body",
      method: "POST",
      path: "/v1/chat-messages",
    });
  } finally {
    globalThis.fetch = previousFetch;
  }

  const headers = new Headers(calls[0]?.headers);
  expect(headers.get("content-type")).toBe("application/json");
  expect(headers.get("authorization")).toBeNull();
  expect(headers.get("x-omi-client-id")).toBeNull();
  expect(calls[0]?.credentials).toBe("omit");
});

test("web scan delegates to the browser capability adapter", async () => {
  let requests = 0;
  const adapter = createWebNativeAdapter({
    bluetooth: {
      requestDevice: async () => {
        requests += 1;
        return {};
      },
    },
  });

  await expect(adapter.startScan()).resolves.toEqual([]);
  expect(requests).toBe(1);
});

test("web native boundary never invents a connected Omi device", async () => {
  const snapshot = await omiNative.getSnapshot();

  expect(snapshot.devices).toEqual([]);
  expect(snapshot.capture).toBe("idle");
});
