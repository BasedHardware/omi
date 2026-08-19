import { expect, test } from "bun:test";
import {
  BrowserScanError,
  type BrowserScanFailureReason,
  createWebNativeAdapter,
  omiBackend,
  omiNative,
} from "../../react-native/src/omiNative.web";

async function expectScanFailure(
  scan: Promise<unknown>,
  reason: BrowserScanFailureReason
): Promise<void> {
  const error = await scan.then(
    () => null,
    (failure) => failure
  );

  expect(error).toBeInstanceOf(BrowserScanError);
  expect((error as BrowserScanError).reason).toBe(reason);
}

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

test("web scan preserves successful browser chooser behavior", async () => {
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
  await expect(adapter.getSnapshot()).resolves.toMatchObject({
    bluetooth: "selected",
    devices: [],
  });
});

test("web scan rejects cancellation and clears a stale browser selection", async () => {
  let requests = 0;
  const adapter = createWebNativeAdapter({
    bluetooth: {
      requestDevice: async () => {
        requests += 1;
        if (requests === 1) {
          return {};
        }
        throw new DOMException("The chooser was dismissed", "NotFoundError");
      },
    },
  });

  await expect(adapter.startScan()).resolves.toEqual([]);
  await expectScanFailure(adapter.startScan(), "cancelled");
  await expect(adapter.getSnapshot()).resolves.toMatchObject({
    bluetooth: "available",
    devices: [],
  });
});

test("web scan rejects browser permission denial with its typed reason", async () => {
  const adapter = createWebNativeAdapter({
    bluetooth: {
      requestDevice: async () => {
        throw new DOMException("Permission denied", "NotAllowedError");
      },
    },
  });

  await expectScanFailure(adapter.startScan(), "denied");
  await expect(adapter.getBluetoothState()).resolves.toBe("denied");
});

test("web scan rejects browser chooser errors with its typed reason", async () => {
  const adapter = createWebNativeAdapter({
    bluetooth: {
      requestDevice: async () => {
        throw new Error("chooser failed");
      },
    },
  });

  await expectScanFailure(adapter.startScan(), "error");
  await expect(adapter.getBluetoothState()).resolves.toBe("error");
});

test("web scan rejects when browser Bluetooth is unsupported", async () => {
  const adapter = createWebNativeAdapter({});

  await expectScanFailure(adapter.startScan(), "unsupported");
  await expect(adapter.getBluetoothState()).resolves.toBe("unsupported");
});

test("web native boundary never invents a connected Omi device", async () => {
  const snapshot = await omiNative.getSnapshot();

  expect(snapshot.devices).toEqual([]);
  expect(snapshot.capture).toBe("idle");
});
