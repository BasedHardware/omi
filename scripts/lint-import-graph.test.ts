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

/**
 * RULE 16 — the port registry. PROVISIONAL; see the fence's own header.
 *
 * These three tests are the fence's red-proof and its false-positive guard, and
 * the second matters as much as the first. This repo has shipped a fence that
 * banned an ordinary English word and fired on prose while catching no real
 * reference, and a guard that fires on prose gets routed around.
 */
const portFixture = join(platformRoot, "scripts", "port-registry-tripwire-fixture.ts");
const runLint = () =>
  spawnSync("bun", ["run", "scripts/lint-import-graph.ts"], { cwd: platformRoot, encoding: "utf8" });

const withPortFixture = (source: string, assertion: (result: ReturnType<typeof runLint>) => void): void => {
  try {
    writeFileSync(portFixture, source);
    assertion(runLint());
  } finally {
    rmSync(portFixture, { force: true });
  }
};

test("rule 16 catches a second composition of a registered port", () => {
  // red-proof, mechanised: this is the exact shape that was deleted from
  // apps/qa/recall-service.ts. Also applied by hand against the real file and
  // observed failing on both the annotated-literal and arrow-return forms.
  withPortFixture(
    [
      'import type { ApplicationReadPorts } from "../core/retrieve/application-read";',
      "export const second = (): ApplicationReadPorts => {",
      "  const ports: ApplicationReadPorts = {} as ApplicationReadPorts;",
      "  return ports;",
      "};",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      const output = `${result.stdout}${result.stderr}`;
      expect(output).toContain("second composition of registered port `ApplicationReadPorts`");
      // Both syntactic forms, not just the one that happens to come first.
      expect(output).toContain("port-registry-tripwire-fixture.ts:2");
      expect(output).toContain("port-registry-tripwire-fixture.ts:3");
    },
  );
});

test("rule 16 does not fire on prose, on a commented-out composition, or on a parameter type", () => {
  // THE FALSE-POSITIVE GUARD. All three of these are real shapes in the tree:
  // the registered composition's own header names the port type five times, an
  // old composition is exactly the kind of thing that gets commented out before
  // it is deleted, and `core/retrieve/application-read.ts` takes the port as a
  // PARAMETER on a line that also ends in `=>`.
  withPortFixture(
    [
      'import type { ApplicationReadPorts } from "../core/retrieve/application-read";',
      "/**",
      " * ApplicationReadPorts used to be built here, as",
      " * `const ports: ApplicationReadPorts = { … }`, before the collapse.",
      " */",
      "// const ports: ApplicationReadPorts = {",
      "// export const old = (): ApplicationReadPorts => ({});",
      "export const consume = (ports: ApplicationReadPorts): number => Object.keys(ports).length;",
      "export const hold: { readonly ports: ApplicationReadPorts | null } = { ports: null };",
    ].join("\n"),
    (result) => {
      expect(`${result.stdout}${result.stderr}`).not.toContain("second composition");
      expect(result.status).toBe(0);
    },
  );
});

test("rule 16's escape hatch is honoured, and only with a reason", () => {
  withPortFixture(
    [
      'import type { ApplicationReadPorts } from "../core/retrieve/application-read";',
      "// port-composition-ok(fixture: proves the hatch is read from the line above)",
      "export const above: ApplicationReadPorts = {} as ApplicationReadPorts;",
      "export const trailing: ApplicationReadPorts = {} as ApplicationReadPorts; // port-composition-ok(same line)",
    ].join("\n"),
    (result) => {
      expect(`${result.stdout}${result.stderr}`).not.toContain("second composition");
      expect(result.status).toBe(0);
    },
  );
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
