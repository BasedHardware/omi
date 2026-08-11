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

test("authority fences reject issuer construction and raw PostgreSQL capabilities outside their owners", () => {
  const issuerFixture = join(platformRoot, "scripts", "authorized-ledger-issuer-tripwire-fixture.ts");
  const postgresFixture = join(platformRoot, "apps", "service", "routes", "postgres-transaction-tripwire-fixture.ts");
  try {
    writeFileSync(issuerFixture, [
      'import * as authorityInternals from "../apps/service/auth/authorized-context-internal";',
      "export const issuer = authorityInternals;",
    ].join("\n"));
    writeFileSync(postgresFixture, [
      'import { withAuthorizedSerializableTransaction } from "../../../drivers/postgres/transaction";',
      "export const raw = withAuthorizedSerializableTransaction;",
    ].join("\n"));
    const result = runLint();
    expect(result.status).not.toBe(0);
    const output = `${result.stdout}${result.stderr}`;
    expect(output).toContain("ledger context minting module is private");
    expect(output).toContain("application code may not import the raw PostgreSQL");
  } finally {
    rmSync(issuerFixture, { force: true });
    rmSync(postgresFixture, { force: true });
  }
});

test("query evaluation constructors are private to the single composition root", () => {
  const routeFixture = join(platformRoot, "apps", "service", "routes", "query-evaluation-tripwire-fixture.ts");
  const copyFixture = join(platformRoot, "apps", "service", "composition", "memory-query-evaluation-copy.ts");
  try {
    writeFileSync(routeFixture, [
      'import * as ownerSource from "../workers/memory-owner-query-evidence-source";',
      'import { defineMemoryAuthorizedQueryGroundingProducer as makeProducer } from "../workers/memory-authorized-query-grounding-producer";',
      'import "../workers/memory-paired-query-grounding-coordinator";',
      'export const dynamic = () => import("../workers/memory-owner-query-evidence-source");',
      "export const bypass = { ownerSource, makeProducer };",
    ].join("\n"));
    writeFileSync(copyFixture, [
      'import { defineMemoryPairedQueryGroundingCoordinator } from "../workers/memory-paired-query-grounding-coordinator";',
      "export const copy = defineMemoryPairedQueryGroundingCoordinator;",
    ].join("\n"));
    const rejected = runLint();
    expect(rejected.status).not.toBe(0);
    const output = `${rejected.stdout}${rejected.stderr}`;
    expect(output).toContain("apps/service/routes/query-evaluation-tripwire-fixture.ts: low-level query-evaluation constructors are private");
    expect(output).toContain("apps/service/composition/memory-query-evaluation-copy.ts: low-level query-evaluation constructors are private");

    rmSync(copyFixture, { force: true });
    writeFileSync(routeFixture, [
      'import { composeMemoryQueryEvaluation } from "../composition/memory-query-evaluation";',
      "export const registered = composeMemoryQueryEvaluation;",
    ].join("\n"));
    const accepted = runLint();
    expect(accepted.status).toBe(0);
    expect(`${accepted.stdout}${accepted.stderr}`).not.toContain("low-level query-evaluation constructors are private");
  } finally {
    rmSync(routeFixture, { force: true });
    rmSync(copyFixture, { force: true });
  }
});

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

/**
 * RULE 16's HATCH IS NOW A `(file, line)` REGISTRY, `PORT_COMPOSITION_HATCHES`
 * — no marker, no comment, no text consulted at all. This replaces, rather
 * than tightens further, the marker apparatus that carried TWO consecutive
 * audit-found bypasses in sequence:
 *
 *   AUDIT-16 round 1  bare substring search over raw text — a marker as an
 *                      ordinary string VALUE on the construction line hatched
 *                      it, no pre-existing hatch needed
 *                      (data/run-2026-08-09/AUDIT-rule16-promotion-round1.md)
 *   AUDIT-16 round 2  the round-1 fix's "is this a comment" check
 *                      (`withoutComments()` blanking the line) is string-
 *                      blind: a `/* ... *​/`-SHAPED STRING VALUE blanks
 *                      identically to a real comment, so the marker still
 *                      hatched it wrapped in fake comment syntax
 *                      (data/run-2026-08-09/AUDIT-rule16-promotion-round2.md)
 *
 * Both are rule 17's own round-2 and round-3 findings, ported here one round
 * later each time because the round-1 fix copied rule 17's round-2 fix
 * rather than the final, post-round-5 registry form. This is that form.
 *
 * WHY THE TESTS BELOW DO NOT FIXTURE-TEST "A GENUINE HATCH PASSES", following
 * rule 17's own round-6 reasoning exactly (AUDIT-17 round 6, on deleting the
 * marker apparatus's tests for the identical reason): `PORT_COMPOSITION_HATCHES`
 * is declared once at module scope and read by every file the linter walks in
 * one pass. A test-only row added to make a fixture "hatched" would be a
 * REAL, PERMANENT exemption for whatever `(file, line)` it names — a standing
 * hole, deliberately added to test the mechanism that closes standing holes.
 * That property (and the stale-row and hatch-scoped-to-its-own-site
 * properties) is instead verified by hand-applied red-proof against a
 * throwaway fixture, recorded in the landing commit rather than left as a
 * permanent registry row nobody can safely remove.
 *
 * Both fixtures below are BOTH ROUNDS' bypass shapes, both now REJECTED
 * regardless of marker text — because no text is read at all, the round-1
 * (plain string) and round-2 (comment-shaped string) classes collapse into
 * the same outcome rather than needing two different checks to close two
 * different string shapes.
 */
test("rule 16, round 1's bypass shape: a plain-string marker on the construction line no longer hatches anything", () => {
  // red-proof: this is AUDIT-16 round 1's exact fixture. Reverting `hatched()`
  // to any text-based check (this file's own git history) makes this fixture
  // pass again; the registry never reads it at all, so no marker text of any
  // shape can hatch without a corresponding PORT_COMPOSITION_HATCHES row.
  withPortFixture(
    [
      'import type { ApplicationReadPorts } from "../core/retrieve/application-read";',
      'export const rogue: ApplicationReadPorts = { bannerNotAComment: "port-composition-ok(fake, not a real comment)",',
      "  x: 1 } as unknown as ApplicationReadPorts;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("second composition of registered port `ApplicationReadPorts`");
    },
  );
});

test("rule 16, round 2's bypass shape: a comment-shaped string marker no longer hatches anything either", () => {
  // AUDIT-16 round 2's exact fixture (data/run-2026-08-09/AUDIT-rule16-promotion-round2.md):
  // `/* ... */`-shaped text INSIDE a string value, which `withoutComments()`
  // blanked identically to a real comment under the round-1 fix. The registry
  // has no comment-detection step to fool — this fires for the same reason
  // the plain-string case above does, not because of a second, separate check.
  withPortFixture(
    [
      'import type { ApplicationReadPorts } from "../core/retrieve/application-read";',
      'export const rogue: ApplicationReadPorts = { banner: "/* port-composition-ok(fake, this is a string not a comment) */",',
      "  x: 1 } as unknown as ApplicationReadPorts;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("second composition of registered port `ApplicationReadPorts`");
    },
  );
});

test("rule 16's second-composition detection is not vacuous: the same shape with no marker text at all still fires", () => {
  // Isolates the registry migration from the detector itself. Without this,
  // "the two fixtures above fire" could mean the checker rejects every
  // second composition unconditionally, registry or not.
  withPortFixture(
    [
      'import type { ApplicationReadPorts } from "../core/retrieve/application-read";',
      'export const noMarker: ApplicationReadPorts = { bannerNotAComment: "just an ordinary string, no marker here",',
      "  x: 1 } as unknown as ApplicationReadPorts;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("second composition of registered port `ApplicationReadPorts`");
    },
  );
});

/**
 * RULE 17 — the wire-path fence. PROVISIONAL; see the fence's own header and
 * `core-foundation/docs/agents/rule-17-wire-path-fence.md`.
 *
 * DOOR's doc recorded four red-proofs as applied BY HAND against the real
 * files (retired door, unmounted door, stale row, hatch-is-load-bearing) but
 * left none of them mechanised, and flagged the comment-stripping exemption
 * as UNPROVEN: "No file in the tree today names a registered wire path only
 * in prose while also constructing a server, so the exemption is currently
 * unexercised." These tests are AUDIT-17's mechanised versions, run against a
 * disposable fixture rather than the real doors, plus the previously-missing
 * comment-only case.
 */
const wirePathFixture = join(platformRoot, "scripts", "wire-path-tripwire-fixture.ts");
const withWirePathFixture = (source: string, assertion: (result: ReturnType<typeof runLint>) => void): void => {
  try {
    writeFileSync(wirePathFixture, source);
    assertion(runLint());
  } finally {
    rmSync(wirePathFixture, { force: true });
  }
};

/**
 * RULE 17 HAS NO LIVE HATCH ROW TODAY. The nine tests that used to live here —
 * every one of them a bypass a non-author audit found in a comment marker across
 * four rounds — are deleted rather than kept. They exercised machinery that does
 * not exist: `wire-path-ok(` in a string, in a block comment inside a string, in
 * a template literal, behind a desynced `${}` interpolation. A test for a deleted
 * mechanism is not coverage, it is a claim about nothing.
 *
 * A future exemption would be a `(file, line)` row in `WIRE_PATH_HATCHES`, but
 * the current registry is intentionally empty. The three cases below cannot be
 * fixture-tested by adding a row: a test-only row would be a permanent real
 * exemption on a path that only exists during a test run — reintroducing, for
 * the sake of testing a fence, exactly the kind of standing hole the fence is
 * about.
 *
 * So they are hand-applied red-proofs, run against real source and recorded in
 * the commit that landed them, the same way this fence's sharpest proof has been
 * handled in every round:
 *
 *   - a SECOND server beside a future exempted construction -> must fire
 *   - move a future row one line off its construction        -> "stale row"
 *   - delete a future row                                    -> the real probe fires
 *
 * The stale-row check earned its place before it was ever tested: the first
 * version of the row named the wrong line, and the checker said so on its first
 * run rather than silently exempting a line that had moved.
 */
test("rule 17 catches a hand-rolled door that serves the registered path without reaching the registered route", () => {
  // Mechanised version of DOOR's red-proof 1/2 (the retired serve.ts shape):
  // stands up a server, names the registered path in code, imports nothing
  // that reaches apps/service/routes/memories.ts.
  withWirePathFixture(
    [
      'Bun.serve({',
      '  port: 9001,',
      '  fetch(req) {',
      '    const url = new URL(req.url);',
      '    if (url.pathname === "/v1/memories") {',
      '      return new Response(JSON.stringify({ id: "raw-fixture-row-id" }));',
      '    }',
      '    return new Response("not found", { status: 404 });',
      '  },',
      '});',
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      const output = `${result.stdout}${result.stderr}`;
      expect(output).toContain("stands up an HTTP server and names the registered wire path");
      expect(output).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17 does not fire when the file only names the path in a comment (comment-stripping exemption, mechanised)", () => {
  // Resolves DOOR's flagged-unproven case. The registered path never appears
  // in code -- only in a comment -- alongside an unrelated server and an
  // unrelated served path. If comment-stripping were not applied, this
  // fixture would false-positive (verified by hand during the audit by
  // temporarily disabling withoutComments() for rule 17 and re-running: the
  // identical fixture then failed lint, naming this file).
  withWirePathFixture(
    [
      "// This server answers /v1/memories -- named only in this comment.",
      "// Never in actual code below.",
      'Bun.serve({',
      '  port: 9002,',
      '  fetch(req) {',
      '    const url = new URL(req.url);',
      '    if (url.pathname === "/totally-unrelated-endpoint") {',
      '      return new Response("ok");',
      '    }',
      '    return new Response("not found", { status: 404 });',
      '  },',
      '});',
    ].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17 does not fire on a file that only CALLS the path (a client, not a door)", () => {
  withWirePathFixture(
    ['export async function callIt(baseUrl: string) {', '  return fetch(`${baseUrl}/v1/memories`);', "}"].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17 does not call a router plus its binder two servers", () => {
  // Round-7 audit. The round-6 "two constructions on one line" check summed all
  // four detection patterns, but `new Hono(` builds a router VALUE and binds no
  // socket. `Bun.serve({ fetch: new Hono().fetch })` is the ordinary way to wire
  // them and is ONE server; the check called it two and fired — unconditionally,
  // on any file in the tree, not only ones naming a wire path. This fixture does
  // not contain the word "memories" at all.
  withWirePathFixture(
    [
      'import { Hono } from "hono";',
      "const server = Bun.serve({ fetch: new Hono().fetch });",
      "void server;",
    ].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17's ambiguity check does not run on files with no registered wire path", () => {
  // Round-9 audit, and the ROOT of rounds 7 and 8 rather than a third instance.
  // The ambiguity check protects WIRE_PATH_HATCHES, whose key is (file, line). A
  // file naming no registered path can never hold a hatch row, so it has nothing
  // to protect — yet the check ran there, unconditionally, tree-wide, and twice
  // fired on ordinary code. Both earlier fixes narrowed which patterns COUNT;
  // neither narrowed where the check RUNS, so the shape recurred through whatever
  // the last fix had just added. This fixture contains no "memories" at all.
  withWirePathFixture(
    [
      'import { Hono } from "hono";',
      "const publicApp = new Hono(); const adminApp = new Hono();",
      "export { publicApp, adminApp };",
    ].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: two unbound routers on one line is still ambiguous", () => {
  // Round-8 audit. Round 7 narrowed the ambiguity count to socket binds, which
  // was right for `Bun.serve({ fetch: new Hono().fetch })` — and reopened round
  // 6's class for lines with NO socket bind: two independent routers collapse to
  // one site, so one future hatch row would exempt both. Not reachable in the
  // tree today because WIRE_PATH_HATCHES is empty; it goes live the first time
  // anyone hatches a Hono-only site.
  withWirePathFixture(
    [
      'import { Hono } from "hono";',
      "const legit = new Hono(); const rogue = new Hono();",
      'rogue.get("/v1/memories", () => new Response("{}"));',
      "export default legit;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("two HTTP servers are constructed on one line");
    },
  );
});

test("rule 17 still catches a Hono-only door that never calls Bun.serve", () => {
  // The converse, and the reason `new Hono(` stays in DETECTION: a router
  // carrying the registered path is the door regardless of who binds it later.
  // Narrowing the count must not narrow what counts as a site.
  withWirePathFixture(
    [
      'import { Hono } from "hono";',
      "const app = new Hono();",
      'app.get("/v1/memories", () => new Response("{}"));',
      "export default app;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17 does not fire on a DIFFERENT route that merely starts with a registered path", () => {
  // `/v1/memories-legacy-export` contains `/v1/memories` as a substring and is
  // not it. No such path exists in the tree today; the guard is here so the
  // first one added does not arrive as a mystery failure somewhere unrelated.
  withWirePathFixture(
    [
      "const server = Bun.serve({",
      "  hostname: \"127.0.0.1\",",
      "  port: 0,",
      "  fetch: (request: Request) => new URL(request.url).pathname === \"/v1/memories-legacy-export\"",
      "    ? Response.json({ ok: true })",
      "    : new Response(\"\", { status: 404 }),",
      "});",
      "void server;",
    ].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
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
