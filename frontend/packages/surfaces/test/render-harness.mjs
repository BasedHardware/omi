import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";
import { act, createElement } from "react";
import { createServer } from "vite";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(packageRoot, "../../..");
const dependencyDistCheck = resolve(repoRoot, "integration/check-surfaces-dependency-dist.mjs");

let viteServer;

function assertDependencyDistIsCurrent() {
  const result = spawnSync(process.execPath, [dependencyDistCheck], {
    cwd: repoRoot,
    encoding: "utf8",
    env: process.env,
  });
  assert.equal(
    result.status,
    0,
    `render harness refuses missing or stale workspace dependency dist:\n${result.stdout}${result.stderr}`,
  );
}

async function server() {
  if (viteServer) return viteServer;
  assertDependencyDistIsCurrent();
  viteServer = await createServer({
    root: packageRoot,
    configFile: resolve(packageRoot, "vite.config.ts"),
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  return viteServer;
}

export async function loadProductionExport(moduleName, exportName) {
  const module = await (await server()).ssrLoadModule(`/src/production/${moduleName}`);
  assert.equal(typeof module[exportName], "function", `${moduleName} must export ${exportName}`);
  return module[exportName];
}

function installDomGlobals(window) {
  const names = [
    "document",
    "location",
    "navigator",
    "Node",
    "Element",
    "HTMLElement",
    "HTMLInputElement",
    "Event",
    "InputEvent",
    "KeyboardEvent",
    "MouseEvent",
    "MutationObserver",
    "getComputedStyle",
    "requestAnimationFrame",
    "cancelAnimationFrame",
  ];
  const previous = new Map();
  previous.set("window", Object.getOwnPropertyDescriptor(globalThis, "window"));
  Object.defineProperty(globalThis, "window", { configurable: true, value: window });
  for (const name of names) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, {
      configurable: true,
      value: typeof window[name] === "function" ? window[name].bind(window) : window[name],
    });
  }
  previous.set("IS_REACT_ACT_ENVIRONMENT", Object.getOwnPropertyDescriptor(globalThis, "IS_REACT_ACT_ENVIRONMENT"));
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, value: true });

  return () => {
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  };
}

export async function renderComponent(Component, props) {
  const dom = new JSDOM("<!doctype html><html><body><div id=\"root\"></div></body></html>", {
    pretendToBeVisual: true,
    url: "http://127.0.0.1/",
  });
  const restoreGlobals = installDomGlobals(dom.window);
  const container = dom.window.document.querySelector("#root");
  assert.ok(container);
  const { createRoot } = await import("react-dom/client");
  const root = createRoot(container);
  await act(async () => {
    root.render(createElement(Component, props));
  });

  return {
    container,
    window: dom.window,
    async act(callback) {
      await act(callback);
    },
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      restoreGlobals();
    },
  };
}

export async function closeRenderHarness() {
  if (!viteServer) return;
  await viteServer.close();
  viteServer = undefined;
}
