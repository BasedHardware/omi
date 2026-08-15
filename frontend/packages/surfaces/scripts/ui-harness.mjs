#!/usr/bin/env node
/**
 * Agent entry point for the surface-lab UI harness.
 *
 * Commands:
 *   manifest [--out path]
 *   capture [--id id] [--out dir] [--limit n]
 *   capture --shell [--id id] [--out dir] [--limit n]
 *   diff --before dir --after dir [--out dir]
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { generateManifest, packageRoot } from "./lib/ui-harness-catalog.mjs";
import { captureBrowser, captureShell, diffRuns, parseArgs } from "./lib/ui-harness-run.mjs";

const HELP = `ui-harness — enumerate, capture, and diff every lab fixture state

Usage (from the platform repo root):
  node frontend/packages/surfaces/scripts/ui-harness.mjs <command>

Commands:
  manifest [--out path]
      Write the generated state manifest JSON (every surface × state ×
      platform × locale × polish flag the lab can render). Default:
      frontend/packages/surfaces/.build/ui-harness/manifest.json

  capture [--id <id>] [--out <dir>] [--limit <n>]
      Headless Chrome capture of every manifest entry (or one id). Writes
      <id>.png and summary.json into a gitignored .build directory.

  capture --shell [--id <id>] [--out <dir>] [--limit <n>]
      Same states through the built macOS shell (WKWebView.takeSnapshot).
      Mobile entries are skipped: native fixture windows cannot be 390×844.

  diff --before <dir> --after <dir> [--out <dir>]
      Per-pixel RGBA compare of two capture runs. Writes diff.json and a
      side-by-side PNG for each changed id. No baselines live in git.

See docs/ui-harness.md.
`;

function writeJson(file, value) {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
  return file;
}

async function main(argv) {
  const args = parseArgs(argv);
  const command = args._[0];
  if (!command || args.help) {
    process.stdout.write(HELP);
    process.exit(command ? 0 : 2);
  }
  if (command === "manifest") {
    const manifest = await generateManifest();
    const out = args.out
      ? resolve(args.out)
      : resolve(packageRoot, ".build/ui-harness/manifest.json");
    writeJson(out, manifest);
    process.stdout.write(`MANIFEST ${manifest.count} states -> ${out}\n`);
    return;
  }
  if (command === "capture") {
    const options = { outDir: args.out, id: args.id, limit: args.limit };
    const summary = args.shell ? await captureShell(options) : await captureBrowser(options);
    process.stdout.write(
      `CAPTURE mode=${summary.mode} states=${summary.count} wallClockMs=${summary.wallClockMs} out=${summary.outDir} errors=${summary.errorCount}\n`,
    );
    if (summary.errorCount > 0) {
      for (const entry of summary.entries) {
        for (const error of entry.consoleErrors) process.stdout.write(`CONSOLE_ERROR ${entry.id}: ${error}\n`);
      }
    }
    return;
  }
  if (command === "diff") {
    if (!args.before || !args.after) throw new Error("diff requires --before and --after capture directories");
    const summary = diffRuns(args.before, args.after, { outDir: args.out });
    process.stdout.write(
      `DIFF method=${summary.method} changed=${summary.changedCount} unchanged=${summary.unchangedCount} out=${summary.outDir}\n`,
    );
    for (const change of summary.changed) {
      process.stdout.write(`CHANGED ${change.id} pixels=${change.changedPixels}/${change.totalPixels} delta=${change.delta}\n`);
    }
    return;
  }
  throw new Error(`unknown command '${command}'`);
}

try {
  await main(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`ERROR: ${error.message}\n`);
  process.exit(1);
}
