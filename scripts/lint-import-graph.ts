import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const forbiddenParentTargets = [".." + "/.private", ".." + "/benchmark"];
const files = (directory: string): string[] => readdirSync(directory, { withFileTypes: true })
  .flatMap((entry) => entry.isDirectory()
    ? entry.name === "node_modules" ? [] : files(join(directory, entry.name))
    : entry.name.endsWith(".ts") ? [join(directory, entry.name)] : []);

const failures: string[] = [];
for (const file of files(root)) {
  const text = readFileSync(file, "utf8");
  const shown = relative(root, file);
  if (shown.startsWith("core/") && /from\s+["'][^"']*drivers\//.test(text)) {
    failures.push(`${shown}: core may not import drivers`);
  }
  if (forbiddenParentTargets.some((target) => text.includes(target))) {
    failures.push(`${shown}: prohibited corpus path reference`);
  }
}
if (failures.length) throw new Error(failures.join("\n"));
