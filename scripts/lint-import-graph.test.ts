import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const platformRoot = new URL("..", import.meta.url).pathname;

test("T0 static tripwire passes the clean platform tree", () => {
  const result = spawnSync("bun", ["run", "scripts/lint-import-graph.ts"], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(result.stderr).toBe("");
});

test("T0 adversarial tripwire catches an injected forbidden bare corpus root in a non-TypeScript platform source", () => {
  const fixture = join(platformRoot, "scripts", "import-graph-tripwire-fixture.json");
  const forbidden = ["omi", "real", "djz", "dev", "v1"].join("-");
  try {
    writeFileSync(fixture, JSON.stringify({ forbidden }));
    const result = spawnSync("bun", ["run", "scripts/lint-import-graph.ts"], { cwd: platformRoot, encoding: "utf8" });
    expect(result.status).not.toBe(0);
    expect(`${result.stdout}${result.stderr}`).toContain("prohibited corpus path reference");
  } finally {
    rmSync(fixture, { force: true });
  }
});

test("T0 adversarial tripwire catches each prohibited path fragment", () => {
  const fixture = join(platformRoot, "scripts", "import-graph-tripwire-fixture.json");
  const fragments = ["." + "private", "bench" + "mark"];
  for (const forbidden of fragments) {
    try {
      writeFileSync(fixture, JSON.stringify({ forbidden }));
      const result = spawnSync("bun", ["run", "scripts/lint-import-graph.ts"], { cwd: platformRoot, encoding: "utf8" });
      expect(result.status).not.toBe(0);
    } finally { rmSync(fixture, { force: true }); }
  }
});
