// Visual audit for the v5 UI: renders every scenario in scenarios.ts through
// the design preview (react-native-web + example data, no backend) and saves
// PNGs, frames.json and a gallery.
//
//   bun pwa/visual-audit/capture.ts [--out DIR] [--only id,id] [--base DIR]
//                                   [--url http://127.0.0.1:PORT] [--scale 2]
//
// Without --url it starts the pwa Vite dev server on a free port and stops it
// afterwards. --base DIR pairs each shot with the same file from an earlier
// run in gallery.html (before | after). Output must live outside the repo.
// Needs Google Chrome (CHROME_PATH overrides the default macOS location).

import { spawn, type Subprocess } from "bun";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { scenarios, type AuditScenario } from "./scenarios";

const pwaDir = resolve(import.meta.dir, "..");
const v5Dir = resolve(pwaDir, "..");
const args = process.argv.slice(2);
const flag = (name: string) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};

const chrome =
  process.env.CHROME_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
if (!existsSync(chrome)) {
  console.error(`Chrome not found at ${chrome}; set CHROME_PATH.`);
  process.exit(2);
}
const out = resolve(
  flag("--out") ?? mkdtempSync(join(tmpdir(), "omi-v5-visual-audit-"))
);
if (!relative(v5Dir, out).startsWith("..")) {
  console.error(`--out must be outside the repository: ${out}`);
  process.exit(2);
}
mkdirSync(out, { recursive: true });
const only = flag("--only")?.split(",").filter(Boolean);
const base = flag("--base") ? resolve(flag("--base")!) : null;
const scale = Number(flag("--scale") ?? "2");
const selected = scenarios.filter(
  (scenario) => !only || only.includes(scenario.id)
);
if (selected.length === 0) {
  console.error(`No scenarios match --only ${only?.join(",")}`);
  process.exit(2);
}

async function waitFor(url: string, seconds: number) {
  for (let attempt = 0; attempt < seconds * 2; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await Bun.sleep(500);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function ensureWorkspaceBuilt() {
  // The preview imports built workspace packages (packages/*/dist).
  if (existsSync(join(v5Dir, "packages/adapters-platform/dist"))) return;
  console.log("Building workspace packages…");
  const build = spawn(
    [
      "bash",
      "-c",
      "bun run --cwd packages/contracts/ratified build && bun x tsc -b",
    ],
    {
      cwd: v5Dir,
      stdout: "inherit",
      stderr: "inherit",
    }
  );
  if ((await build.exited) !== 0) throw new Error("Workspace build failed");
}

async function startVite(): Promise<{ url: string; server: Subprocess }> {
  const port = 5200 + Math.floor(Math.random() * 700);
  const server = spawn(
    [
      "bunx",
      "vite",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--strictPort",
    ],
    {
      cwd: pwaDir,
      stdout: "ignore",
      stderr: "ignore",
    }
  );
  const url = `http://127.0.0.1:${port}`;
  await waitFor(`${url}/design-preview.html`, 60);
  return { url, server };
}

async function shoot(
  url: string,
  file: string,
  viewport: AuditScenario["viewport"]
) {
  // One throwaway profile per shot: a shared profile's lock makes the next
  // headless Chrome wait forever.
  const profile = mkdtempSync(join(tmpdir(), "omi-v5-audit-chrome-"));
  rmSync(file, { force: true });
  const browser = spawn(
    [
      chrome,
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      "--no-first-run",
      "--no-default-browser-check",
      `--force-device-scale-factor=${scale}`,
      `--window-size=${viewport.width},${viewport.height}`,
      "--virtual-time-budget=6000",
      `--user-data-dir=${profile}`,
      `--screenshot=${file}`,
      url,
    ],
    { stdout: "ignore", stderr: "ignore" }
  );
  // Headless Chrome writes the PNG once virtual time runs out, but the Vite
  // HMR socket can keep it alive afterwards; stop it once the file is stable.
  const deadline = Date.now() + 30_000;
  let lastSize = -1;
  while (Date.now() < deadline && browser.exitCode === null) {
    await Bun.sleep(250);
    const size = existsSync(file) ? Bun.file(file).size : -1;
    if (size > 0 && size === lastSize) break;
    lastSize = size;
  }
  browser.kill();
  await browser.exited;
  rmSync(profile, { recursive: true, force: true });
  if (!existsSync(file)) throw new Error(`No screenshot written for ${file}`);
}

type Frame = {
  id: string;
  title: string;
  appearance: string;
  file: string;
  url: string;
  viewport: AuditScenario["viewport"];
};

function gallery(frames: Frame[]) {
  const baseFiles =
    base && existsSync(base) ? new Set(readdirSync(base)) : new Set<string>();
  const cells = frames
    .map((frame) => {
      const before = baseFiles.has(frame.file)
        ? `<figure><img src="${join(
            base!,
            frame.file
          )}" loading="lazy"><figcaption>before</figcaption></figure>`
        : "";
      return `<section><h2>${frame.id} · ${frame.appearance}</h2><p>${
        frame.title
      }</p><div class="pair">${before}<figure><img src="${
        frame.file
      }" loading="lazy"><figcaption>${
        before ? "after" : ""
      }</figcaption></figure></div></section>`;
    })
    .join("\n");
  return `<!doctype html><meta charset="utf-8"><title>Omi v5 visual audit</title>
<style>body{font:14px -apple-system,sans-serif;margin:24px;background:#f2f2f2;color:#111}
section{margin:0 0 40px}h2{font-size:15px;margin:0 0 4px}p{margin:0 0 10px;color:#555}
.pair{display:flex;gap:16px;align-items:flex-start}figure{margin:0;flex:1;max-width:900px}
img{width:100%;border:1px solid #ccc;border-radius:6px;background:#fff}figcaption{color:#777;font-size:12px}</style>
<h1>Omi v5 visual audit</h1>${cells}`;
}

await ensureWorkspaceBuilt();
const external = flag("--url");
const vite = external ? null : await startVite();
const origin = external ?? vite!.url;
const frames: Frame[] = [];
let failures = 0;
try {
  for (const scenario of selected) {
    for (const appearance of scenario.appearances) {
      const file = `${scenario.id}-${appearance}.png`;
      const url = `${origin}/design-preview.html?${scenario.query}&appearance=${appearance}&notice=off`;
      try {
        await shoot(url, join(out, file), scenario.viewport);
        frames.push({
          id: scenario.id,
          title: scenario.title,
          appearance,
          file,
          url,
          viewport: scenario.viewport,
        });
        console.log(`✓ ${file}`);
      } catch (error) {
        failures += 1;
        console.error(`✗ ${file}: ${(error as Error).message}`);
      }
    }
  }
} finally {
  vite?.server.kill();
}
writeFileSync(join(out, "frames.json"), JSON.stringify(frames, null, 2));
writeFileSync(join(out, "gallery.html"), gallery(frames));
console.log(
  `\n${frames.length} screenshots, ${failures} failed → ${out}/gallery.html`
);
process.exit(failures === 0 ? 0 : 1);
