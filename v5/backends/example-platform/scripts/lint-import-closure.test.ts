import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";

const platformRoot = new URL("..", import.meta.url).pathname;

const FORBIDDEN = [
  "apps/qa",
  "drivers/sqlite",
  "drivers/model/glm",
  "integration/local-test-gateway",
  "harness/",
  "spikes/",
] as const;

test("rule 18 fence is green on the ratified production entrypoints", () => {
  const result = spawnSync("bun", ["run", "scripts/lint-import-closure.ts"], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(result.stderr).toBe("");
});

test("rule 18 negative control: sqlite dream links a forbidden target so a broken tracer cannot go green", () => {
  const result = spawnSync("bun", [
    "run",
    "scripts/trace-value-imports.ts",
    "drivers/sqlite/dream.ts",
    ...FORBIDDEN.flatMap((needle) => ["--forbid", needle]),
  ], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(1);
  const output = `${result.stdout}${result.stderr}`;
  expect(output).toContain("FORBIDDEN");
  expect(output).toContain("drivers/sqlite/dream.ts");
});
