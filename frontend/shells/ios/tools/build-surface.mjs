#!/usr/bin/env node
// Bundles the TS surface into surface/dist/ and (with --ship) copies it into the
// Flutter app's assets so it is served from the app bundle instead of a dev server.
//   node tools/build-surface.mjs            # dev bundle (served by tools/serve.mjs)
//   node tools/build-surface.mjs --ship     # also sync into app/assets/surface/
// Uses `bun build` purely as a zero-install TS transpiler/bundler; a real setup
// would use whatever bundler the shared TS core standardises on.

import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, cpSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'surface/dist');
const ship = process.argv.includes('--ship');
const stamp = new Date().toISOString().replace('T', ' ').slice(0, 19) + 'Z';

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

execFileSync(process.env.BUN ?? 'bun',
  ['build', join(root, 'surface/src/app.ts'), '--outfile', join(dist, 'app.js'), '--target', 'browser', '--format', 'iife'],
  { stdio: 'inherit' });

writeFileSync(join(dist, 'app.js'),
  readFileSync(join(dist, 'app.js'), 'utf8').replaceAll('__BUILD_STAMP__', stamp));
cpSync(join(root, 'surface/index.html'), join(dist, 'index.html'));
console.log(`surface built (stamp ${stamp})`);

if (ship) {
  const assets = join(root, 'app/assets/surface');
  rmSync(assets, { recursive: true, force: true });
  mkdirSync(assets, { recursive: true });
  cpSync(dist, assets, { recursive: true });
  console.log('synced -> app/assets/surface/');
}
