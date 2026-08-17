import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { emittedOutputMismatches } from "./check-surfaces-dependency-dist.mjs";

test("runtime JavaScript must match the fresh compiler emit even when declarations are current", async () => {
  const packagePath = await mkdtemp(join(tmpdir(), "omi-dist-runtime-"));
  const runtimePath = join(packagePath, "index.js");
  const declarationPath = join(packagePath, "index.d.ts");
  try {
    await writeFile(runtimePath, "export const state = 'stale';\n");
    await writeFile(declarationPath, "export declare const state: string;\n");
    const expected = new Map([
      [runtimePath, "export const state = 'current';\n"],
      [declarationPath, "export declare const state: string;\n"],
    ]);

    assert.deepEqual(emittedOutputMismatches("@omi-core/example", packagePath, expected), [
      "stale compiler output — @omi-core/example: index.js differs from current TypeScript emit",
    ]);
  } finally {
    await rm(packagePath, { recursive: true, force: true });
  }
});
