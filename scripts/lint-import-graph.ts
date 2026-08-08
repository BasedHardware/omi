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

const failures: string[] = [];
for (const file of files(root)) {
  const text = readFileSync(file, "utf8");
  const shown = relative(root, file);
  if (shown.startsWith("core/") && /from\s+["'][^"']*drivers\//.test(text)) {
    failures.push(`${shown}: core may not import drivers`);
  }
  if (forbiddenParentTargets.some((target) => text.includes(target)) || corpusRoot.test(text)) {
    failures.push(`${shown}: prohibited corpus path reference`);
  }
}
if (failures.length) throw new Error(failures.join("\n"));
