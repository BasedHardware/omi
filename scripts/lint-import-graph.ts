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

if (failures.length) throw new Error(failures.join("\n"));
