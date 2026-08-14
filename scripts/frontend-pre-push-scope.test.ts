import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { chmodSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const scope = join(root, "scripts/frontend-pre-push-scope");

const runScope = (...files: string[]) =>
  spawnSync(scope, files, { cwd: root, encoding: "utf8" });

test("frontend-pre-push-scope skips backend-only paths", () => {
  chmodSync(scope, 0o755);
  const result = runScope("core/order.ts", "drivers/postgres/transaction.ts", "apps/service/bin/dev-server.ts");
  expect(result.status).toBe(1);
});

test("frontend-pre-push-scope runs for frontend/ and toolchain paths", () => {
  chmodSync(scope, 0o755);
  expect(runScope("frontend/packages/surfaces/src/production/ChatProduction.tsx").status).toBe(0);
  expect(runScope("scripts/pre-push").status).toBe(0);
  expect(runScope(".github/checks-manifest.yaml").status).toBe(0);
  expect(runScope(".github/failure-classes/FC-deploy-concurrency.json").status).toBe(0);
});

test("frontend-pre-push-scope --print keeps only in-scope paths", () => {
  chmodSync(scope, 0o755);
  const result = spawnSync(scope, ["--print", "core/order.ts", "frontend/AGENTS.md", "scripts/pre-push"], {
    cwd: root,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(result.stdout.trim().split("\n")).toEqual(["frontend/AGENTS.md", "scripts/pre-push"]);
});

test("path-scoped pre-push exits 0 on a backend-only file list", () => {
  const list = join(root, "scripts", "pre-push-scope-backend-files.txt");
  writeFileSync(list, "core/order.ts\n");
  try {
    const result = spawnSync("bash", ["scripts/pre-push"], {
      cwd: root,
      encoding: "utf8",
      env: { ...process.env, PRE_PUSH_CHANGED_FILES_FILE: list },
    });
    expect(result.status).toBe(0);
    expect(`${result.stdout}${result.stderr}`).toContain("Skipping frontend pre-push battery");
  } finally {
    spawnSync("rm", ["-f", list]);
  }
});
