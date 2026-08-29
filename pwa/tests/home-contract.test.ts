import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import {
  createBrowserCapabilityAdapter,
  type BrowserEnvironment,
} from "../../react-native/src/browser-adapters.web";

const root = resolve(import.meta.dir, "..");

test("browser capability adapter never invents a pendant or permission", async () => {
  const environment: BrowserEnvironment = {
    bluetooth: undefined,
    mediaDevices: undefined,
    permissions: undefined,
  };
  const adapter = createBrowserCapabilityAdapter(environment);

  expect(adapter.snapshot()).toEqual({
    bluetooth: "unsupported",
    microphone: "unsupported",
  });
  expect(await adapter.chooseBluetoothDevice()).toEqual({
    ok: false,
    reason: "unsupported",
  });
  expect(await adapter.checkMicrophone()).toEqual({
    ok: false,
    reason: "unsupported",
  });
});

test("browser shell keeps the installable document around the RN entry", async () => {
  const html = await readFile(resolve(root, "index.html"), "utf8");
  expect(html).toContain("manifest.webmanifest");
  expect(html).toContain('<div id="app"></div>');
});

test("web entry renders the canonical React Native App", async () => {
  const entry = await readFile(resolve(root, "src/main.ts"), "utf8");

  expect(entry).toContain('from "../../react-native/App"');
  expect(entry).toContain("AppRegistry.registerComponent");
  expect(entry).toContain("AppRegistry.runApplication");
  expect(entry).not.toContain("innerHTML");
  expect(entry).not.toContain("renderApp");
});

test("browser root gives the canonical RN surface the full viewport", async () => {
  const entry = await readFile(resolve(root, "src/main.ts"), "utf8");
  const styles = await readFile(resolve(root, "src/root.css"), "utf8");

  expect(entry).toContain('import "./root.css"');
  expect(styles).toContain("#app");
  expect(styles).toContain("height: 100%");
  expect(styles).toContain("min-height: 100dvh");
  expect(styles).toContain("#app > div");
  expect(styles).toContain("--omi-web-canvas: #0b0f17");
  expect(styles).toContain("--omi-web-surface: #1a1f2e");
  expect(styles).toContain("--omi-web-accent: #6c8eef");
  expect(styles).toContain("overflow: auto");
  expect(styles).not.toContain("background: #141414");
});

test("install metadata presents Omi as a finished product", async () => {
  const html = await readFile(resolve(root, "index.html"), "utf8");
  const manifest = JSON.parse(
    await readFile(resolve(root, "public/manifest.webmanifest"), "utf8")
  );

  expect(html).toContain("<title>Omi</title>");
  expect(html).not.toContain("Omi v5");
  expect(manifest).toMatchObject({
    background_color: "#0b0f17",
    name: "Omi",
    short_name: "Omi",
    theme_color: "#0b0f17",
  });
  expect(manifest.description).not.toBe("Omi v5");
});

test("service worker installs the built application shell for an offline first restart", async () => {
  const source = await readFile(resolve(root, "public/sw.js"), "utf8");
  const listeners = new Map<string, (event: any) => void>();
  const added: string[][] = [];
  const stored: string[] = [];
  let offline = false;
  const worker = {
    addEventListener: (name: string, listener: (event: any) => void) =>
      listeners.set(name, listener),
    clients: { claim: async () => undefined },
    location: { origin: "https://omi.test" },
    skipWaiting: () => undefined,
  };
  const cache = {
    addAll: async (paths: string[]) => added.push(paths),
    put: async (path: string) => stored.push(path),
  };
  const cacheStorage = {
    delete: async () => true,
    keys: async () => [],
    match: async (request: Request | string) =>
      request === "/" ? new Response("cached shell") : undefined,
    open: async () => cache,
  };
  const fetchShell = async () => {
    if (offline) throw new Error("offline");
    return new Response(
      '<link rel="stylesheet" href="/assets/index-abc.css"><script src="/assets/index-def.js"></script>',
      { status: 200 }
    );
  };

  new Function("self", "caches", "fetch", source)(
    worker,
    cacheStorage,
    fetchShell
  );
  let installation: Promise<unknown> | undefined;
  listeners.get("install")?.({
    waitUntil: (promise: Promise<unknown>) => {
      installation = promise;
    },
  });
  await installation;

  expect(stored).toEqual(["/"]);
  expect(added).toEqual([
    [
      "/manifest.webmanifest",
      "/omi-mark.svg",
      "/assets/index-abc.css",
      "/assets/index-def.js",
    ],
  ]);
  offline = true;
  const fetchListener = listeners.get("fetch")!;
  const fetchOffline = (mode: string, path: string) => {
    let response: Promise<Response | undefined> | undefined;
    fetchListener({
      request: {
        method: "GET",
        mode,
        url: `https://omi.test${path}`,
      },
      respondWith: (promise: Promise<Response | undefined>) => {
        response = promise;
      },
    });
    return response!;
  };
  await expect(
    fetchOffline("same-origin", "/assets/missing.js")
  ).rejects.toThrow("PWA resource is unavailable offline");
  await expect(
    fetchOffline("navigate", "/memories").then((value) => value?.text())
  ).resolves.toBe("cached shell");
});
