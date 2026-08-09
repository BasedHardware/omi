import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
// Assemble these tokens so this checker itself remains inside the fence it enforces.
const forbiddenParentTargets = ["." + "private", "bench" + "mark", "omi" + "-real-djz-dev-v1", "hold" + "out-v1"];
// Path-shaped only. The bare word is ordinary vocabulary here — the ratified contract's
// own fixture sets are called corpora — so matching it as a word banned prose, comments
// and identifiers while catching no actual data reference. What must stay forbidden is a
// *path* into an evaluation corpus: a trailing separator, or the bare word quoted as a
// standalone path segment. Narrowed 2026-08-08 after it false-positived four integration
// files; the dataset names above remain unambiguous substring matches.
const corpusRoot = new RegExp(`${"corp" + "ora"}[/\\\\]|["'\`]${"corp" + "ora"}["'\`]`);
const sourceExtensions = new Set([".ts", ".tsx", ".js", ".json"]);
const files = (directory: string): string[] => readdirSync(directory, { withFileTypes: true })
  .flatMap((entry) => entry.isDirectory()
    ? entry.name === "node_modules" ? [] : files(join(directory, entry.name))
    : sourceExtensions.has(entry.name.slice(entry.name.lastIndexOf("."))) ? [join(directory, entry.name)] : []);

/**
 * THE VISIBLE-DERIVATION FENCE.
 *
 * Every value that can reach the wire must be derived from the AUTHORIZED
 * PROJECTION, never from raw storage.
 *
 * This is not a style preference. A real authorization oracle shipped in this
 * repo on 2026-08-08: the declared frontier (emitted in the page body) and three
 * signed cursor bindings were derived from the SQLite loader's
 * `coherent_snapshot_digest` and from `internal_coverage.durable.ledger_head`.
 * Both cover rows the reader is not authorized to see, so a record hidden by
 * policy produced different bytes than a record that never existed — publishing
 * the existence of hidden data. Measured: digests 3ad6626b… vs 1441b306…, ledger
 * sequence 6 vs 5.
 *
 * The leaking version looked entirely reasonable in review: the snapshot digest
 * is stable, honestly named, and right there. Nothing about it reads as a
 * security decision, which is exactly why a convention is not enough and this is
 * a fence.
 *
 * Safe provenance: `projected.graph_generation`,
 * `projected.projected_content_digest`, and anything computed purely from the
 * visible closure. `core/` is already fenced off from `drivers/` by the rule
 * above, so the exposure lives in composition code under `apps/`.
 *
 * Escape hatch, mirroring the repo's `// domain-pending(<ID>)` idiom: a genuine
 * internal-coherence use must justify itself inline with
 * `// storage-provenance-ok(<reason>)` on the same line. Comments are exempt
 * wholesale — prose cannot leak a byte, and documenting why the fence exists is
 * worth more than a grep-clean file.
 */
/**
 * Widened 2026-08-08 after an audit showed the fence was narrower than the rule:
 * a composition could emit `durable_snapshot.claims.length` under another name,
 * pass lint, and republish hidden-row cardinality. Verified by experiment — lint
 * stayed green while proof 6 failed. Proof 6 is the backstop, but a fence that
 * only catches the one instance already fixed is not a ratchet.
 *
 * These are the loader's storage-scoped surfaces. Legitimate uses exist (the
 * durable snapshot IS the input to the authorization boundary), and they carry
 * an inline justification — which is the point: a reviewer sees every place
 * storage state enters composition code.
 */
/**
 * ── RULE 16: THE PORT REGISTRY ───────────────────────────────────────────────
 *
 * **A registered port has exactly ONE composition.** Two modules independently
 * constructing the same port type are two implementations, not two adapters.
 *
 * PROVISIONAL — landed 2026-08-08. It runs immediately; it has been red-proofed
 * and its false positives audited across `platform/` and `core-foundation/`
 * (see `core-foundation/docs/agents/rule-16-port-registry.md`), but it is new,
 * so if it fires on another lane that is a swarm-wide blocker, never something
 * to route around.
 *
 * WHY THIS IS A FENCE AND NOT A CONVENTION. `ApplicationReadPorts` was
 * constructed independently by the REST door (`apps/service/composition/
 * memory-read.ts`) and the MCP door (`apps/qa/recall-service.ts`). Both were
 * green. Both were reviewed. They disagreed on the digest scheme, the
 * declared-frontier derivation, the coverage default and the opaque-ref codecs,
 * and the result was measured: over ONE snapshot and ONE principal the two doors
 * returned the SAME memory — byte-identical text, identical render hash — under
 * DIFFERENT public item ids (`mem1_eca59618fff27e10…` vs
 * `mem1_dd73274cc9b1a9ac…`). Every node-level cross-door assertion passed the
 * whole time, because the divergence sat one layer below where anyone looked.
 *
 * OPT-IN, DELIBERATELY. A row is added when a port acquires a SECOND
 * construction site, not before. A registry that tried to cover every port the
 * moment it was declared would fire constantly on ordinary single-implementation
 * code and be routed around within a day, and a routed-around guardrail is worse
 * than none. The small, boring edit of adding a row is the ratchet.
 *
 * WHAT COUNTS AS A CONSTRUCTION SITE — three syntactic forms, matched on
 * COMMENT-STRIPPED text:
 *   `: Port = {`        an annotated binding to an object literal
 *   `): Port =>`        a function declaring the port as its return type
 *   `satisfies Port`    a satisfies-checked literal
 * Casts (`as Port`) are deliberately NOT construction: a cast is how a hostile
 * or partial value is fed to the port's own defensive checks, and banning it
 * would ban the tests that prove those checks work.
 *
 * COMMENTS ARE EXEMPT WHOLESALE. This repo has already shipped a fence that
 * banned an ordinary English word and fired on prose while catching no real
 * reference. Prose cannot construct anything, and documenting why a port has one
 * composition is worth more than a grep-clean file — the module header of the
 * one registered composition names the port type five times.
 *
 * TESTS ARE EXEMPT. A test double is a second implementation ON PURPOSE: the
 * port's own contract test builds hostile, partial and lookalike port records to
 * prove the core rejects them, which is the opposite of the defect this rule
 * exists for. A test cannot serve a user a divergent id. What the exemption
 * gives up — "do the two doors actually agree?" — is not a fence question at
 * all; it is an assertion, and it lives in
 * `apps/service/composition/cross-door-identity.test.ts`.
 *
 * ESCAPE HATCH, mirroring the repo's `// domain-pending(<ID>)` and
 * `// storage-provenance-ok(<reason>)` idioms:
 * `// port-composition-ok(<reason>)` on the binding line or the line above.
 */
interface PortRegistryRow {
  readonly portType: string;
  /** Paths, relative to the platform root, allowed to construct this port. */
  readonly composedIn: readonly string[];
  readonly reason: string;
}
const PORT_REGISTRY: readonly PortRegistryRow[] = [
  {
    portType: "ApplicationReadPorts",
    composedIn: ["apps/service/composition/memory-read.ts"],
    reason:
      "The REST and MCP doors both read through this port. Two compositions minted "
      + "different public item ids for the same memory; the transports "
      + "(apps/mcp/protocol.ts, apps/service/routes/memories.ts) stay separate, "
      + "everything below them is shared.",
  },
];
/**
 * ── RULE 17: THE WIRE-PATH FENCE ─────────────────────────────────────────────
 *
 * **A settled wire path is SERVED by exactly one route module.** A file that
 * both stands up an HTTP server and names a registered wire path in code must
 * reach that path through the registered route module — it may not answer the
 * path itself.
 *
 * PROVISIONAL — landed 2026-08-08 with the W4 rebuild. Per §8 it runs
 * immediately and is PROVISIONAL until a NON-AUTHOR has read it against the
 * English statement above and audited its false positives. If it fires on
 * another lane, that is a swarm-wide blocker, never something to route around.
 *
 * WHY RULE 16 COULD NOT SEE THE DEFECT THIS EXISTS FOR. Rule 16 keys on
 * REGISTERED PORT TYPES. `integration/server/serve.ts` answered `/v1/memories`
 * — the settled client recall route, the one `make stack` and HOW-TO-RUN.md
 * boot — from a hand-rolled handler over a hand-rolled `McpProtocolPorts`. It
 * composed no registered port, so it was invisible to rule 16 BY
 * CONSTRUCTION, and the checker was green the entire time the door was serving
 * raw fixture row ids as public item ids. A door that composes nothing
 * registered is exactly the door a port registry cannot see; the wire path is
 * the coordinate that catches it. (fable, W4: "key the fence on the wire path
 * as well as the port type".)
 *
 * WHAT TRIGGERS IT — BOTH halves, on COMMENT-STRIPPED text:
 *   1. the file constructs an HTTP server (`Bun.serve(`, `new Hono(`,
 *      `Deno.serve(`, `createServer(`), AND
 *   2. it names a registered wire path.
 * A file that only CALLS the path is a client, not a door, and is not the
 * defect class: `apps/service/bin/boot-acceptance.ts` fetches `/v1/memories`
 * all day and can never serve anyone a divergent id.
 *
 * WHAT SATISFIES IT: being the registered route module itself, or importing it
 * (directly, or through a server factory registered in `boundVia`). That is
 * deliberately an IMPORT check rather than a behavioural one — a pin on
 * behaviour is rule 16's rejected alternative restated one layer up, and the
 * W4 ruling rejected it again for exactly this door.
 *
 * COMMENTS ARE EXEMPT WHOLESALE, and TESTS ARE EXEMPT — same reasons as rule
 * 16. Prose cannot serve a byte, and a test double is a second implementation
 * on purpose. Whether the doors actually agree is an assertion, not a fence
 * question, and it lives in
 * `integration/adversarial/cross-door-identity.test.ts`.
 *
 * ESCAPE HATCH: a row in `WIRE_PATH_HATCHES` below, keyed by (file, LINE).
 * There is no marker, no comment, and no text to parse.
 *
 * IT USED TO BE A COMMENT MARKER, and four rounds of non-author audit found four
 * working bypasses in it, each one the same question — *is this marker really
 * inside a comment?* — answered a little better and broken again:
 *
 *   round 1  the marker was file-wide, so one legitimate hatch made the whole
 *            file a permanent blind spot for every server added to it later
 *   round 2  a bare substring search, so `banner: "wire-path-ok(fake)"` on the
 *            construction line hatched it — no pre-existing hatch needed
 *   round 3  `withoutComments` is string-blind, so `"/* wire-path-ok(fake) *​/"`
 *            as a STRING VALUE satisfied "present raw, absent stripped"
 *   round 4  the comment scanner tracked template literals but not `${…}` DEPTH,
 *            so an unmatched backtick desynced it — and the proof type-checked
 *
 * Every fix was correct and every one left a smaller hole. That is convergence
 * toward a real lexer, written to guard the mechanism whose entire job is to
 * SWITCH A FENCE OFF. The audit's ruling, and it is right: there is no bound
 * short of a real lexer that is not arbitrary, and "we stopped finding bypasses"
 * is the specific failure mode this program exists to catch, not a stopping
 * condition.
 *
 * So the exemption stops being text. To exempt a construction site you edit this
 * file, which is a visible diff in the one file everybody already watches.
 *
 * KEYED BY LINE, NOT BY FILE — and this is not a detail. A file-keyed table would
 * be correct for rule 16 ("one module owns this port's composition" is naturally
 * a per-file question) and would silently REOPEN ROUND 1 here, because rule 17's
 * subject is a specific HTTP server instance and one file may legitimately hold
 * several unrelated ones.
 *
 * The locality cost is real and was accepted with eyes open: the justification no
 * longer sits beside the code it justifies. A short pointer comment at the site
 * keeps a reader oriented, and it is deliberately NOT read by this checker — a
 * comment that does no work cannot be forged into doing any.
 */
interface WirePathRegistryRow {
  /** The settled path, spelled exactly as the route registers it. */
  readonly wirePath: string;
  /** The one module that owns this path's request handling. */
  readonly servedBy: string;
  /**
   * Import-specifier fragments that count as reaching the registered route:
   * the route module itself, plus the server factories that mount it.
   */
  readonly boundVia: readonly string[];
  readonly reason: string;
}
const WIRE_PATH_REGISTRY: readonly WirePathRegistryRow[] = [
  {
    wirePath: "/v1/memories",
    servedBy: "apps/service/routes/memories.ts",
    boundVia: ["routes/memories", "app-facing"],
    reason:
      "The integration harness served this path from a hand-rolled handler that minted "
      + "public item ids from raw fixture row ids, while the registered route minted "
      + "reader-scoped opaque refs. Both were green; the harness was the door humans "
      + "dogfooded. Rule 16 could not see it because it composed no registered port.",
  },
];
/**
 * Server-construction sites exempted from rule 17. Keyed by (file, 1-indexed
 * line). A stale row — one whose line no longer holds a server construction —
 * is itself a failure, symmetric with `servedBy` and `composedIn`: a registry
 * row that has quietly stopped describing reality disables a fence silently,
 * which is the whole class this file exists to prevent.
 */
interface WirePathHatchRow {
  /** Path relative to the platform root, exactly as the checker reports it. */
  readonly file: string;
  /** 1-indexed line of the server construction being exempted. */
  readonly line: number;
  readonly reason: string;
}
const WIRE_PATH_HATCHES: readonly WirePathHatchRow[] = [
  {
    file: "integration/adversarial/live-server.ts",
    line: 67,
    reason:
      "A port probe that answers a constant empty body to every request and is stopped "
      + "before it is used. The `/v1/memories` reference below it is this file CALLING "
      + "the route as a client; nothing here serves that path, and a test-support client "
      + "cannot hand anyone a divergent public id.",
  },
];
/**
 * `code.includes("/v1/memories")` also matches `/v1/memories-legacy-export`,
 * which is a DIFFERENT route that merely starts with the registered one. Found
 * by the non-author audit, which built the collision rather than assuming it.
 * No such path exists in the tree today; the check is here so the first one
 * added does not arrive as a mystery failure in an unrelated file.
 *
 * A trailing `/` still counts as the same path — `/v1/memories/` is the
 * registered route's own trailing-slash case, which the real route answers 404
 * and a rogue door might answer 200. Exempting it would exempt a real defect.
 */
const namesWirePath = (code: string, wirePath: string): boolean => {
  let from = 0;
  for (;;) {
    const at = code.indexOf(wirePath, from);
    if (at < 0) return false;
    const next = code[at + wirePath.length];
    if (next === undefined || !/[A-Za-z0-9_-]/.test(next)) return true;
    from = at + 1;
  }
};
/**
 * Anything that means "a server lives here" for DETECTION purposes. `new Hono(`
 * belongs: a router carrying the path is the door, whoever binds it.
 */
const serverConstructionPatterns: readonly RegExp[] = [
  /\bBun\.serve\s*\(/,
  /\bDeno\.serve\s*\(/,
  /\bnew\s+Hono\s*\(/,
  /\bcreateServer\s*\(/,
];

/**
 * The subset that actually BINDS A SOCKET — and the distinction is load-bearing
 * for counting, not for detection.
 *
 * `new Hono(` constructs a router VALUE. It opens nothing; something else binds
 * it, and `Bun.serve({ fetch: new Hono().fetch })` is the ordinary way to write
 * that. On one line it matches two patterns, so a naive count says "two servers"
 * about a file containing exactly one. The round-6 fix did precisely that, and
 * the round-7 audit caught it: an unconditional check, firing on working code,
 * anywhere in `platform/` — not even scoped to files that name a wire path.
 *
 * That is the failure this repo has already shipped once, in a fence that banned
 * an ordinary English word and fired on prose while catching no real reference.
 * A guard that fires on ordinary code gets routed around, and a routed-around
 * guardrail is worse than none.
 *
 * Two independent SOCKET BINDS on one line still has no ordinary explanation and
 * still fails.
 */
const socketBindPatterns: readonly RegExp[] = [
  /\bBun\.serve\s*\(/,
  /\bDeno\.serve\s*\(/,
  /\bcreateServer\s*\(/,
];

const portCompositionAllowMarker = "port-composition-ok(";
const portConstructionPatterns = (portType: string): readonly RegExp[] => [
  new RegExp(`:\\s*${portType}\\s*=\\s*\\{`),
  new RegExp(`\\)\\s*:\\s*${portType}\\s*=>`),
  new RegExp(`\\bsatisfies\\s+${portType}\\b`),
];

const storageProvenanceIdentifiers = [
  "coherent_snapshot_digest",
  "internal_coverage",
  "ledger_head",
  "durable_snapshot",
  "stm_rows",
  "graph_heads",
  "eligible_items",
  "scan_ceiling",
];
const storageProvenanceAllowMarker = "storage-provenance-ok(";

/** Blank out comments so documentation of the fence does not trip the fence. */
const withoutComments = (text: string): string => text
  .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
  .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead: string) => lead + " ".repeat(match.length - lead.length));

const failures: string[] = [];
/** Rule 16 bookkeeping: which registered rows were seen constructed, and where. */
const portConstructionSites = new Map<string, string[]>(
  PORT_REGISTRY.map((row) => [row.portType, []]),
);
/** Rule 17 bookkeeping: whether each registered path was seen in its own route module. */
const wirePathServedBySeen = new Set<string>();
for (const file of files(root)) {
  const text = readFileSync(file, "utf8");
  const shown = relative(root, file);
  if (shown.startsWith("core/") && /from\s+["'][^"']*drivers\//.test(text)) {
    failures.push(`${shown}: core may not import drivers`);
  }

  // ── Rule 16: a registered port has exactly one composition ────────────────
  if (/\.tsx?$/.test(shown) && !/\.test\.tsx?$/.test(shown)) {
    const rawLines = text.split("\n");
    const codeLines = withoutComments(text).split("\n");
    const hatched = (index: number): boolean =>
      (rawLines[index] ?? "").includes(portCompositionAllowMarker)
      || (rawLines[index - 1] ?? "").includes(portCompositionAllowMarker);
    for (const row of PORT_REGISTRY) {
      const patterns = portConstructionPatterns(row.portType);
      codeLines.forEach((line, index) => {
        if (!patterns.some((pattern) => pattern.test(line))) return;
        portConstructionSites.get(row.portType)!.push(shown);
        if (row.composedIn.includes(shown) || hatched(index)) return;
        failures.push(
          `${shown}:${index + 1}: second composition of registered port \`${row.portType}\`. `
          + `A registered port has exactly ONE composition (rule 16); this one lives in `
          + `${row.composedIn.join(", ")}. ${row.reason} `
          + `Call the registered composition instead of building a parallel one. If this `
          + `genuinely is not a second implementation, justify it with `
          + `// ${portCompositionAllowMarker}<reason>) on this line.`,
        );
      });
    }
  }
  // ── Rule 17: a settled wire path is served by exactly one route module ────
  if (/\.tsx?$/.test(shown) && !/\.test\.tsx?$/.test(shown)) {
    const code = withoutComments(text);
    const codeLines = code.split("\n");

    // Every line that stands up a server. The hatch is judged against each of
    // these, not against the file, so one justified server cannot exempt the
    // next one somebody adds.
    /**
     * Matches per line, not merely whether a line matches. `(file, line)` is the
     * hatch's key, so a line holding TWO constructions has one entry and one
     * exemption covering both — a row written for a legitimate server would also
     * cover an unrelated rogue one sharing its line. Found by the round-6 audit,
     * demonstrated against the real hatched file, lint green.
     */
    const constructionsOn = (line: string): number =>
      socketBindPatterns.reduce(
        (total, pattern) => total + (line.match(new RegExp(pattern.source, "g")) ?? []).length,
        0,
      );
    const serverSites = codeLines
      .map((line, index) => (serverConstructionPatterns.some((p) => p.test(line)) ? index : -1))
      .filter((index) => index >= 0);

    // Two constructions on one line is ALWAYS a failure, hatch or no hatch. The
    // registry's safety property assumes one line, one construction, and nothing
    // was checking that assumption. Removing the ambiguity beats patching around
    // it — the same reasoning that replaced the comment marker with this table.
    /**
     * Unbound routers, counted separately. Round 7 narrowed the ambiguity check
     * to socket binds — correct, because a router nested inside its own binder's
     * call is not a second server. But `serverSites` still detects on all four
     * patterns, so two independent, UNBOUND `new Hono(` calls on one line
     * collapsed to a single site with no socket bind to count, reopening round
     * 6's class at exactly the seam round 7 left open.
     *
     * Only when there is no socket bind on the line: with one present, the
     * router is overwhelmingly its argument, which is the case round 7 exists to
     * permit.
     */
    const routersOn = (line: string): number =>
      (line.match(/\bnew\s+Hono\s*\(/g) ?? []).length;
    const ambiguousSiteCount = (line: string): number => {
      const binds = constructionsOn(line);
      return binds > 0 ? binds : routersOn(line);
    };
    /**
     * SCOPE, and this is the root rounds 7 and 8 each patched a symptom of.
     *
     * The ambiguity check exists to protect `WIRE_PATH_HATCHES`, whose key is
     * (file, line). A file that names no registered wire path can never hold a
     * hatch row, so it has nothing to protect — and running the check there made
     * it an unconditional, tree-wide gate that twice fired on ordinary code
     * (round 7: a router and its binder; round 9: two plain router declarations).
     *
     * Both fixes narrowed WHICH PATTERNS COUNT. Neither narrowed WHERE THE CHECK
     * RUNS, so the same shape recurred through whatever the last fix added, and
     * the next framework pattern anyone registers would have reopened it a third
     * time. Gating on relevance ends the class rather than the instance.
     *
     * `live-server.ts` stays in scope — it names the path as a client call — so
     * round 6's protection is unaffected.
     */
    const fileNamesARegisteredPath = WIRE_PATH_REGISTRY.some(
      (row) => namesWirePath(code, row.wirePath),
    );
    for (const index of fileNamesARegisteredPath ? serverSites : []) {
      if (ambiguousSiteCount(codeLines[index] ?? "") < 2) continue;
      failures.push(
        `${shown}:${index + 1}: two HTTP servers are constructed on one line. `
        + `WIRE_PATH_HATCHES is keyed by (file, line), so a single exemption would `
        + `cover both — including one nobody justified. Put each construction on `
        + `its own line.`,
      );
    }

    /**
     * The marker on the construction line, or anywhere in the comment block
     * immediately above it. Walking the block matters: the tree's one real hatch
     * is a four-line `//` comment whose marker sits on the FIRST line, so
     * checking only `index - 1` (rule 16's rule, adequate for a one-line
     * justification) would reject a hatch that is correctly placed.
     */
    // No text is consulted. A site is exempt iff this file declares it, by line.
    const hatchedAt = (index: number): boolean =>
      WIRE_PATH_HATCHES.some((row) => row.file === shown && row.line === index + 1);

    // A hatch row that no longer names a server construction has silently stopped
    // exempting anything — or worse, is exempting a line that moved. Same
    // treatment as a stale `servedBy` or `composedIn`: say so, loudly.
    for (const row of WIRE_PATH_HATCHES) {
      if (row.file !== shown) continue;
      if (serverSites.includes(row.line - 1)) continue;
      failures.push(
        `${shown}:${row.line}: stale WIRE_PATH_HATCHES row — no server is constructed here. `
        + `A hatch that has stopped describing reality disables a fence silently. `
        + `Move the row to the construction's current line, or delete it.`,
      );
    }

    const unhatchedSite = serverSites.find((index) => !hatchedAt(index));
    const standsUpAServer = serverSites.length > 0;
    for (const row of WIRE_PATH_REGISTRY) {
      if (shown === row.servedBy && namesWirePath(code, row.wirePath)) {
        wirePathServedBySeen.add(row.wirePath);
      }
      if (!standsUpAServer || !namesWirePath(code, row.wirePath)) continue;
      if (shown === row.servedBy || unhatchedSite === undefined) continue;
      const reachesRegisteredRoute = row.boundVia.some((specifier) =>
        new RegExp(`from\\s+["'][^"']*${specifier}["']`).test(code));
      if (reachesRegisteredRoute) continue;
      failures.push(
        `${shown}:${unhatchedSite + 1}: stands up an HTTP server and names the registered wire path `
        + `\`${row.wirePath}\` without reaching its registered route module `
        + `(${row.servedBy}). A settled wire path is SERVED by exactly one route module `
        + `(rule 17). ${row.reason} `
        + `Import and register the real route instead of answering the path here. If THIS `
        + `server genuinely does not serve that path, add a row to WIRE_PATH_HATCHES in `
        + `scripts/lint-import-graph.ts keyed by (file, line). The hatch is per `
        + `construction site, not per file: a file-wide one would exempt the next server `
        + `somebody adds here.`,
      );
    }
  }

  // The fence protects WIRE COMPOSITION. Two exemptions, both principled rather
  // than convenient:
  //
  //  - Type declarations. An `interface CoherentQaLoad { … internal_coverage … }`
  //    describes the SHAPE of the loader's output; no value flows and nothing can
  //    reach a client. Firing there produced six markers whose only honest reason
  //    would have been "this is a type", which trains people to mark reflexively
  //    and destroys the signal.
  //  - Test files. A test asserting the loader's own output is exactly where
  //    referencing storage internals is correct, and a test cannot ship a leak.
  //
  // Everything else under apps/ is composition and stays fenced.
  const isTestFile = /\.test\.tsx?$/.test(shown);
  if (shown.startsWith("apps/") && !isTestFile) {
    // Identifiers are matched on the comment-stripped text; the allow marker is
    // matched on the ORIGINAL line, because the marker itself is a comment and
    // stripping first would make it permanently unfindable. Accepted either
    // trailing on the same line or on the line immediately above, since the
    // justified expressions are often too long for a trailing comment.
    const rawLines = text.split("\n");
    const lines = withoutComments(text).split("\n");
    // Blank out `interface X { … }` / `type X = { … }` bodies by brace balance,
    // so a declaration cannot trip a fence about values.
    let typeDepth = 0;
    let inTypeDeclaration = false;
    const typeLines = lines.map((line) => {
      if (!inTypeDeclaration && /^\s*(export\s+)?(declare\s+)?(interface|type)\s+\w/.test(line)) {
        inTypeDeclaration = true;
        typeDepth = 0;
      }
      if (!inTypeDeclaration) return line;
      const opens = (line.match(/\{/g) ?? []).length;
      const closes = (line.match(/\}/g) ?? []).length;
      typeDepth += opens - closes;
      const terminates = (typeDepth <= 0 && (closes > 0 || /;\s*$/.test(line) || /^\s*type\s+\w+\s*=\s*[^{]+;/.test(line)));
      if (terminates) inTypeDeclaration = false;
      return "";
    });
    const justified = (index: number): boolean =>
      (rawLines[index] ?? "").includes(storageProvenanceAllowMarker)
      || (rawLines[index - 1] ?? "").includes(storageProvenanceAllowMarker);
    typeLines.forEach((line, index) => {
      if (justified(index)) return;
      for (const identifier of storageProvenanceIdentifiers) {
        if (line.includes(identifier)) {
          failures.push(
            `${shown}:${index + 1}: storage-provenance value \`${identifier}\` in wire-composition code. `
            + "Everything reaching the wire must derive from the authorized projection "
            + "(projected.graph_generation / projected.projected_content_digest), never raw storage. "
            + "If this is a genuine internal-coherence use, justify it with "
            + "// storage-provenance-ok(<reason>) on this line.",
          );
        }
      }
    });
  }
  if (forbiddenParentTargets.some((target) => text.includes(target)) || corpusRoot.test(text)) {
    failures.push(`${shown}: prohibited corpus path reference`);
  }
}
// A row whose declared composition no longer constructs the port is a STALE row,
// and a stale row silently disables the rule for that port — the failure mode
// the wire-seam registry calls "the selector is probably stale". Fail on it.
for (const row of PORT_REGISTRY) {
  const seen = portConstructionSites.get(row.portType) ?? [];
  for (const declared of row.composedIn) {
    if (!seen.includes(declared)) {
      failures.push(
        `PORT_REGISTRY row \`${row.portType}\` declares ${declared} as its composition, `
        + "but no construction site was found there. Either the composition moved (update the "
        + "row) or the port is no longer composed (delete the row) — a stale row silently "
        + "disables rule 16 for this port.",
      );
    }
  }
}

// Same staleness rule as rule 16's, for the same reason: a row whose declared
// route module no longer names the path silently disables the fence for that
// path, and a fence that has quietly stopped fencing is worse than none.
for (const row of WIRE_PATH_REGISTRY) {
  if (!wirePathServedBySeen.has(row.wirePath)) {
    failures.push(
      `WIRE_PATH_REGISTRY row \`${row.wirePath}\` declares ${row.servedBy} as its route `
      + "module, but that file does not name the path. Either the route moved (update the "
      + "row) or the path is gone (delete the row) — a stale row silently disables rule 17 "
      + "for this path.",
    );
  }
}

if (failures.length) throw new Error(failures.join("\n"));
