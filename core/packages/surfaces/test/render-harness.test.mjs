import assert from "node:assert/strict";
import test from "node:test";

import { loadCheckedExport, renderComponent } from "./render-harness.mjs";

function assertDescriptorRestored(name, before) {
  const after = Object.getOwnPropertyDescriptor(globalThis, name);
  assert.equal(after?.configurable, before?.configurable, `${name} configurable descriptor is restored`);
  assert.equal(after?.enumerable, before?.enumerable, `${name} enumerable descriptor is restored`);
  assert.equal(after?.writable, before?.writable, `${name} writable descriptor is restored`);
  assert.equal(after?.value, before?.value, `${name} value is restored`);
  assert.equal(after?.get, before?.get, `${name} getter is restored`);
  assert.equal(after?.set, before?.set, `${name} setter is restored`);
}

test("every production export load rechecks dependency dist", async () => {
  let stale = false;
  let checks = 0;
  let loads = 0;
  const dependencies = {
    assertCurrent() {
      checks += 1;
      if (stale) throw new Error("BROKEN dist:surface-deps stale mid-run");
    },
    async loadModule() {
      loads += 1;
      return { Example() {} };
    },
  };

  assert.equal(typeof await loadCheckedExport("Example.tsx", "Example", dependencies), "function");
  stale = true;
  await assert.rejects(
    loadCheckedExport("Example.tsx", "Example", dependencies),
    /BROKEN dist:surface-deps stale mid-run/,
  );
  assert.equal(checks, 2, "the cached server does not cache the dependency check");
  assert.equal(loads, 1, "the stale second import is refused before module loading");
});

test("a component that throws while rendering does not leak jsdom globals", async () => {
  const names = ["window", "document", "navigator", "IS_REACT_ACT_ENVIRONMENT"];
  const before = new Map(names.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
  function ThrowsMidRender() {
    throw new Error("M6 render explosion");
  }

  await assert.rejects(renderComponent(ThrowsMidRender, {}), /M6 render explosion/);

  for (const name of names) assertDescriptorRestored(name, before.get(name));
});
