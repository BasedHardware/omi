import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import viteConfig from "../vite.config";
import {
  createWebNativeAdapter,
  isBluetoothScanAvailable,
  omiBackend,
} from "../../react-native/src/omiNative.web";

const root = resolve(import.meta.dir, "..");
const webModulePath = resolve(root, "../react-native/src/omiNative.web.ts");

async function webSource(): Promise<string> {
  return readFile(webModulePath, "utf8");
}

test("Vite aliases React Native directly to React Native Web", () => {
  const config = viteConfig({
    command: "serve",
    env: {
      OMI_LOCAL_API_CLIENT_ID: "test-client",
      OMI_LOCAL_API_TOKEN: "test-token",
    },
  });
  const alias = config.resolve?.alias;

  expect(alias).toEqual(
    expect.objectContaining({
      "react-native": expect.stringContaining("node_modules/react-native-web"),
    })
  );
});

test("web native exports do not retain redundant web aliases", async () => {
  const source = await webSource();

  expect(source).not.toContain("omiBackendWeb");
  expect(source).not.toContain("omiNativeWeb");
});

test("canonical native state types do not include browser capability states", async () => {
  const source = await readFile(
    resolve(root, "../react-native/src/omiNativeTypes.ts"),
    "utf8"
  );

  expect(source).not.toContain("'unsupported'");
  expect(source).not.toContain("'available'");
  expect(source).not.toContain("'selected'");
});

test("unsupported web operations share the explicit rejection behavior", async () => {
  const adapter = createWebNativeAdapter({});

  await expect(adapter.connectDevice("device-1")).rejects.toThrow(
    "Omi device capture is unavailable in the browser"
  );
  await expect(adapter.stopCapture()).rejects.toThrow(
    "Omi capture is unavailable in the browser"
  );
  await expect(adapter.stopScan()).rejects.toThrow(
    "Omi device capture is unavailable in the browser"
  );
});

test("web Bluetooth capability remains distinct from native power and permission states", async () => {
  const available = createWebNativeAdapter({
    bluetooth: {
      requestDevice: async () => ({}),
    },
  });
  const unsupported = createWebNativeAdapter({});

  await expect(available.getBluetoothState()).resolves.toBe("available");
  await expect(available.getSnapshot()).resolves.toMatchObject({
    bluetooth: "available",
  });
  await expect(unsupported.getBluetoothState()).resolves.toBe("unsupported");
  await expect(unsupported.getSnapshot()).resolves.toMatchObject({
    bluetooth: "unsupported",
  });
});

test("platform Bluetooth scan capability includes web available and selected states", () => {
  expect(isBluetoothScanAvailable("poweredOn")).toBe(true);
  expect(isBluetoothScanAvailable("available")).toBe(true);
  expect(isBluetoothScanAvailable("selected")).toBe(true);
  expect(isBluetoothScanAvailable("poweredOff")).toBe(false);
  expect(isBluetoothScanAvailable("unsupported")).toBe(false);
});

test("web permissions report unsupported or unknown instead of fabricated denial", async () => {
  const unsupported = createWebNativeAdapter({});
  const failed = createWebNativeAdapter({
    mediaDevices: {
      getUserMedia: async () => {
        throw new Error("browser probe failed");
      },
    },
  });

  await expect(unsupported.requestPermissions()).resolves.toEqual({
    microphone: "unsupported",
    notifications: "unknown",
  });
  await expect(failed.requestPermissions()).resolves.toEqual({
    microphone: "unknown",
    notifications: "unknown",
  });
});

test("web backend normalizes an empty response body to null", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(null, { status: 204 })) as unknown as typeof globalThis.fetch;

  try {
    await expect(
      omiBackend.request({
        id: "empty-response",
        method: "DELETE",
        path: "/v1/chat-generations/generation-1",
      })
    ).resolves.toMatchObject({
      body: null,
      id: "empty-response",
      status: 204,
    });
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("web assets are typed for both Metro numbers and browser URLs", async () => {
  const declaration = await readFile(
    resolve(root, "../react-native/assets.d.ts"),
    "utf8"
  );

  expect(declaration).toContain("const source: string | number;");
});

test("web platform ownership stays in the React Native boundary", async () => {
  const source = await webSource();
  const appSource = await readFile(
    resolve(root, "../react-native/src/app/AppOrchestrator.tsx"),
    "utf8"
  );

  expect(source).not.toContain("../../pwa/src/");
  expect(appSource).toContain(
    "isBluetoothScanAvailable(nativeSnapshot?.bluetooth)"
  );
  expect(await readFile(resolve(root, "src/main.ts"), "utf8")).toContain(
    'from "../../react-native/App"'
  );
});
