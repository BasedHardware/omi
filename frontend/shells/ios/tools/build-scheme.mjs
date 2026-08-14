#!/usr/bin/env node
// Builds the custom-scheme probe surface into three versioned bundle dirs
// under app/assets/ so the shell can exercise the OTA swap + contract gate:
//   bundle-v1  baseline, contract matches
//   bundle-v2  same code, different bundleId + accent color, contract matches
//   bundle-v3  contract version deliberately wrong -> shell must refuse it
// Like build-loop.mjs, each .ts transpiles to its own ESM file (no bundling):
// the webview resolving a real module graph over omi-ui:// is a fact under test.
//   node tools/build-scheme.mjs

import { execFileSync } from 'node:child_process';
import { writeFileSync, readFileSync, mkdirSync, cpSync, rmSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'surface/scheme');
const contract = JSON.parse(readFileSync(join(root, 'contract/bridge.contract.json'), 'utf8'));
const contractVersion = contract.version;

const ts = (file) => execFileSync(process.env.BUN ?? 'bun',
  ['build', file, '--no-bundle', '--target', 'browser'], { encoding: 'utf8' });

// --- v1: transpile the source surface --------------------------------------
const v1 = join(root, 'app/assets/bundle-v1');
rmSync(v1, { recursive: true, force: true });
mkdirSync(v1, { recursive: true });
for (const f of readdirSync(src)) {
  if (f.endsWith('.ts')) writeFileSync(join(v1, f.replace(/\.ts$/, '.js')), ts(join(src, f)));
  else cpSync(join(src, f), join(v1, f));
}
// The generated bridge client rides inside the bundle, like the real core would.
writeFileSync(join(v1, 'bridge.g.js'), ts(join(root, 'surface/src/bridge.g.ts')));
writeFileSync(join(v1, 'manifest.json'),
  JSON.stringify({ bundleId: 'v1', bridgeContractVersion: contractVersion }, null, 2));

// --- v2: same surface, visibly different, same contract ---------------------
const v2 = join(root, 'app/assets/bundle-v2');
rmSync(v2, { recursive: true, force: true });
cpSync(v1, v2, { recursive: true });
writeFileSync(join(v2, 'style.css'),
  readFileSync(join(v1, 'style.css'), 'utf8').replace('--accent: #30d158', '--accent: #0a84ff'));
writeFileSync(join(v2, 'manifest.json'),
  JSON.stringify({ bundleId: 'v2', bridgeContractVersion: contractVersion }, null, 2));

// --- v3: contract mismatch, must never mount --------------------------------
const v3 = join(root, 'app/assets/bundle-v3');
rmSync(v3, { recursive: true, force: true });
cpSync(v1, v3, { recursive: true });
writeFileSync(join(v3, 'manifest.json'),
  JSON.stringify({ bundleId: 'v3', bridgeContractVersion: '9.9.9' }, null, 2));

console.log(`scheme bundles built (contract ${contractVersion}) -> bundle-v1, bundle-v2, bundle-v3`);
