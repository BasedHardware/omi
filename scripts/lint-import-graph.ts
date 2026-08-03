import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
// Assemble these tokens so this checker itself remains inside the fence it enforces.
const forbiddenParentTargets = ["." + "private", "bench" + "mark", "omi" + "-real-djz-dev-v1", "hold" + "out-v1"];
const corpusRoot = new RegExp(`\\b${"corp" + "ora"}\\b`);
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
