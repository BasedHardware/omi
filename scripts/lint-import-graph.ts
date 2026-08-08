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
const storageProvenanceIdentifiers = ["coherent_snapshot_digest", "internal_coverage", "ledger_head"];
const storageProvenanceAllowMarker = "storage-provenance-ok(";

/** Blank out comments so documentation of the fence does not trip the fence. */
const withoutComments = (text: string): string => text
  .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
  .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead: string) => lead + " ".repeat(match.length - lead.length));

const failures: string[] = [];
for (const file of files(root)) {
  const text = readFileSync(file, "utf8");
  const shown = relative(root, file);
  if (shown.startsWith("core/") && /from\s+["'][^"']*drivers\//.test(text)) {
    failures.push(`${shown}: core may not import drivers`);
  }
  if (shown.startsWith("apps/")) {
    // Identifiers are matched on the comment-stripped text; the allow marker is
    // matched on the ORIGINAL line, because the marker itself is a comment and
    // stripping first would make it permanently unfindable. Accepted either
    // trailing on the same line or on the line immediately above, since the
    // justified expressions are often too long for a trailing comment.
    const rawLines = text.split("\n");
    const lines = withoutComments(text).split("\n");
    const justified = (index: number): boolean =>
      (rawLines[index] ?? "").includes(storageProvenanceAllowMarker)
      || (rawLines[index - 1] ?? "").includes(storageProvenanceAllowMarker);
    lines.forEach((line, index) => {
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
if (failures.length) throw new Error(failures.join("\n"));
