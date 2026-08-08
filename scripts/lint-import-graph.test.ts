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

test("rule 17's escape hatch is honoured", () => {
  withWirePathFixture(
    [
      "// wire-path-ok(fixture: proves the file-scoped hatch is read)",
      'Bun.serve({',
      '  port: 9003,',
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

/**
 * THE HATCH IS PER SERVER, NOT PER FILE.
 *
 * A non-author audit HELD rule 17's promotion on exactly this. The hatch was
 * `text.includes(marker)` — file-wide, unconditional, permanent — so the first
 * legitimate justification turned the whole file into a blind spot. The audit
 * proved it by editing the tree's one hatched file so a second server there
 * really did answer the registered path with a raw fixture id: lint stayed
 * green. These two tests are that mutation and its converse, mechanised.
 */
test("rule 17: a hatched server does not exempt a second, unhatched server in the same file", () => {
  withWirePathFixture(
    [
      "const probe = Bun.serve({",
      "  hostname: \"127.0.0.1\",",
      "  port: 0,",
      "  // wire-path-ok(a port probe that answers a constant empty body)",
      "  fetch: () => new Response(\"\"),",
      "});",
      "void probe;",
      "const rogue = Bun.serve({",
      "  hostname: \"127.0.0.1\",",
      "  port: 0,",
      "  fetch: (request: Request) => new URL(request.url).pathname === \"/v1/memories\"",
      "    ? Response.json({ items: [{ id: \"retrieval-node-v1:seed-0000\" }] })",
      "    : new Response(\"\", { status: 404 }),",
      "});",
      "void rogue;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: the hatch marker must be in a COMMENT, not a string literal on the same line", () => {
  // Round-2 audit finding, and worse than round 1: round 1 needed a pre-existing
  // legitimate hatch to hide behind. This needs nothing — any rogue file
  // self-exempts on first write, by putting the marker in a property value on the
  // very line it is exempting.
  withWirePathFixture(
    // The marker MUST sit on the same physical line as the construction, which is
    // the only line `hatchedAt` substring-searches. A first draft of this test put
    // it three lines down; it passed, and the isolation proof (revert the fence,
    // expect exactly one red) stayed green — proving the test, not the fence.
    [
      "const rogue = Bun.serve({ port: 0, banner: \"wire-path-ok(fake, not a real comment)\","
        + " fetch: (request: Request) => new URL(request.url).pathname === \"/v1/memories\"",
      "    ? Response.json({ id: \"raw-fixture-row-id\" })",
      "    : new Response(\"\", { status: 404 }) });",
      "void rogue;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: comment SYNTAX inside a string does not hatch (round-3 audit)", () => {
  // `withoutComments()` is a pair of regexes with no concept of string
  // boundaries, so it blanks block-comment-shaped text wherever it appears —
  // including inside a quoted string. That satisfied the round-2 predicate
  // (present raw, absent stripped) without the marker ever being in a comment.
  // The hatch now needs a second, string-aware mechanism to agree.
  withWirePathFixture(
    [
      "const rogue = Bun.serve({ port: 0, banner: \"/* wire-path-ok(fake) */\","
        + " fetch: (request: Request) => new URL(request.url).pathname === \"/v1/memories\"",
      "    ? Response.json({ id: \"raw-fixture-row-id\" })",
      "    : new Response(\"\", { status: 404 }) });",
      "void rogue;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: a line carrying a backtick cannot hatch (round-4 audit)", () => {
  // `commentMask` tracks template literals but not interpolation DEPTH, so an
  // unmatched backtick inside `${…}` closes the outer literal early and desyncs
  // the scanner — after which a `//` still inside the literal reads as a real
  // comment. The audit's version type-checks cleanly under `tsc --noEmit`, so
  // "it looks bizarre" was the only defence left. The fix removes the class:
  // no line with a backtick may hatch.
  withWirePathFixture(
    [
      "const rogue = Bun.serve({ port: 0, banner: `${String.raw`}//wire-path-ok(fake)",
      "` }rest`, fetch: (request: Request) =>",
      "  new URL(request.url).pathname === \"/v1/memories\"",
      "    ? Response.json({ id: \"raw-fixture-row-id\" })",
      "    : new Response(\"\", { status: 404 }) } as any);",
      "void rogue;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: a genuine trailing BLOCK-comment hatch still works", () => {
  // The converse of the test above. Rejecting all block-comment markers would
  // have been the easy fix and would have broken a legitimate form.
  withWirePathFixture(
    [
      "const probe = Bun.serve({ port: 0, fetch: () => new Response(\"\") });"
        + " /* wire-path-ok(constant empty body; the reference below is a client call) */",
      "void probe;",
      "export const call = (base: string) => fetch(`${base}/v1/memories`);",
    ].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: a template-literal line contiguous with the construction does not hatch", () => {
  // The version of the test below that ACTUALLY reaches the walk-up's
  // string-awareness. In the other one the closing backtick sits on its own line
  // and breaks the comment block first, so it passes without the mask ever being
  // consulted — verified by removing the mask and watching it stay green. Here
  // the backtick shares the marker's line, so the line is blank after stripping,
  // non-blank raw, and directly above the construction: comment-shaped, not a
  // comment. Removing the walk-up's mask check turns this red.
  withWirePathFixture(
    [
      "const banner = `",
      "// wire-path-ok(fake)`;",
      "const rogue = Bun.serve({ port: 0, fetch: (request: Request) =>",
      "  new URL(request.url).pathname === \"/v1/memories\"",
      "    ? Response.json({ id: \"raw-fixture-row-id\" })",
      "    : new Response(\"\", { status: 404 }) });",
      "void rogue; void banner;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: a template-literal line that LOOKS like a comment block does not hatch", () => {
  // Found while fixing round 3; on neither the auditor's list nor mine. A line
  // inside a template literal is blank after `withoutComments()` and non-blank
  // raw, which is exactly what `isCommentText` tested for — so a fake
  // justification could be smuggled in as data on the lines ABOVE the
  // construction, not just on it.
  withWirePathFixture(
    [
      "const banner = `",
      "// wire-path-ok(fake)",
      "`;",
      "const rogue = Bun.serve({ port: 0, fetch: (request: Request) =>",
      "  new URL(request.url).pathname === \"/v1/memories\"",
      "    ? Response.json({ id: \"raw-fixture-row-id\" })",
      "    : new Response(\"\", { status: 404 }) });",
      "void rogue; void banner;",
    ].join("\n"),
    (result) => {
      expect(result.status).not.toBe(0);
      expect(`${result.stdout}${result.stderr}`).toContain("wire-path-tripwire-fixture.ts");
    },
  );
});

test("rule 17: a genuine trailing-comment hatch on the construction line still works", () => {
  // The converse of the test above, and the reason it cannot simply be
  // "reject any marker on the construction line". A guard that rejects a
  // legitimate justification is how a guardrail gets routed around.
  withWirePathFixture(
    [
      "const probe = Bun.serve({ port: 0, fetch: () => new Response(\"\") });"
        + " // wire-path-ok(constant empty body; the reference below is a client call)",
      "void probe;",
      "export const call = (base: string) => fetch(`${base}/v1/memories`);",
    ].join("\n"),
    (result) => {
      expect(result.status).toBe(0);
      expect(`${result.stdout}${result.stderr}`).not.toContain("wire-path-tripwire-fixture.ts");
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
