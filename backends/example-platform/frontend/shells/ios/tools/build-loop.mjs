#!/usr/bin/env node
// Builds the loopback-origin probe surface into app/assets/surface-loop/.
// Unlike build-surface.mjs this does NOT bundle to IIFE: each .ts becomes its
// own ESM file so the webview resolves a real multi-file module graph itself —
// that resolution is one of the facts under test.
//   node tools/build-loop.mjs

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, cpSync, rmSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'surface/loop');
const out = join(root, 'app/assets/surface-loop');

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

for (const f of readdirSync(src)) {
  if (f.endsWith('.ts')) {
    // Transpile only (no bundling): --no-bundle keeps the import graph intact.
    const js = execFileSync(process.env.BUN ?? 'bun',
      ['build', join(src, f), '--no-bundle', '--target', 'browser'],
      { encoding: 'utf8' });
    writeFileSync(join(out, f.replace(/\.ts$/, '.js')), js);
  } else {
    cpSync(join(src, f), join(out, f));
  }
}
// Minimal service worker for the registration probe.
writeFileSync(join(out, 'sw.js'), "self.addEventListener('install', () => {});\n");
console.log('loop surface built ->', out);
