import { expect, test } from "bun:test";
import { omiBackend, omiNative } from "../../react-native/src/omiNative.web";

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
      }),
    ).resolves.toEqual(
      expect.objectContaining({ id: "settings", status: 200 }),
    );
    await expect(
      omiBackend.request({
        headers: { authorization: "Bearer secret" },
        id: "credentialed",
        method: "GET",
        path: "/v1/settings",
      }),
    ).rejects.toThrow("authorization");
  } finally {
    globalThis.fetch = previousFetch;
  }

  expect(calls).toHaveLength(1);
  expect(calls[0]).toEqual(
    expect.objectContaining({
      credentials: "omit",
      input: "/__omi/api/v1/settings",
    }),
  );
  expect(calls[0]?.headers.get("authorization")).toBeNull();
});

test("web native boundary never invents a connected Omi device", async () => {
  const snapshot = await omiNative.getSnapshot();

  expect(snapshot.devices).toEqual([]);
  expect(snapshot.capture).toBe("idle");
});
