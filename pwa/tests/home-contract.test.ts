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
