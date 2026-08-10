import assert from "node:assert/strict";
import test from "node:test";

import { loadCheckedExport } from "./render-harness.mjs";

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
