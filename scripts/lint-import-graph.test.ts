import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";

test("T0 import graph and corpus exclusion lint pass", () => {
  const result = spawnSync("bun", ["run", "scripts/lint-import-graph.ts"], {
    cwd: new URL("..", import.meta.url).pathname,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(result.stderr).toBe("");
});
