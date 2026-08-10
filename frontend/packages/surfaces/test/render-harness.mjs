import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";
import { act, createElement } from "react";
import { createServer } from "vite";
import { dependencyDistFingerprint } from "../../../../integration/check-surfaces-dependency-dist.mjs";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(packageRoot, "../../..");
const dependencyDistCheck = resolve(repoRoot, "integration/check-surfaces-dependency-dist.mjs");

let viteServer;
let verifiedDependencyFingerprint;

function assertDependencyDistIsCurrent() {
  const before = dependencyDistFingerprint();
  if (before === verifiedDependencyFingerprint) return;
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
  const after = dependencyDistFingerprint();
  assert.equal(after, before, "workspace dependency bytes changed while dist freshness was being verified");
  verifiedDependencyFingerprint = after;
}

async function server() {
  if (viteServer) return viteServer;
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

export async function loadCheckedExport(moduleName, exportName, { assertCurrent, loadModule }) {
  assertCurrent();
  const module = await loadModule(moduleName);
  assert.equal(typeof module[exportName], "function", `${moduleName} must export ${exportName}`);
  return module[exportName];
}

export async function loadProductionExport(moduleName, exportName) {
  return loadCheckedExport(moduleName, exportName, {
    assertCurrent: assertDependencyDistIsCurrent,
    loadModule: async (name) => (await server()).ssrLoadModule(`/src/production/${name}`),
  });
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
  let root;
  try {
    const { createRoot } = await import("react-dom/client");
    root = createRoot(container);
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
        try {
          await act(async () => root.unmount());
        } finally {
          dom.window.close();
          restoreGlobals();
        }
      },
    };
  } catch (error) {
    try {
      if (root) await act(async () => root.unmount());
    } catch {
      // Preserve the render/import error; cleanup must not replace it.
    } finally {
      dom.window.close();
      restoreGlobals();
    }
    throw error;
  }
}

export async function closeRenderHarness() {
  if (!viteServer) return;
  await viteServer.close();
  viteServer = undefined;
}
