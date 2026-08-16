import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
let installedVersion = null;
try {
  installedVersion = JSON.parse(readFileSync(resolve(root, "node_modules/typescript/package.json"), "utf8")).version;
} catch {
  // A clean CI checkout installs below.
}

if (installedVersion !== manifest.devDependencies.typescript) {
  run(["install", "--frozen-lockfile", "--ignore-scripts"]);
}
run(["run", "verify"]);

function run(args) {
  const result = spawnSync("bun", args, { cwd: root, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
