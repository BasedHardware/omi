#!/usr/bin/env node
// Copies the real @omi-core/surfaces ship build into app/assets/surfaces/
// so the iOS scheme handler can serve it at omi-ui://local/ (wave-2).
// Expects core/packages/surfaces/dist to already be built.
//   node tools/build-surfaces-bundle.mjs
// Optional: SURFACES_DIST=/abs/path/to/dist

import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const contract = JSON.parse(readFileSync(join(root, 'contract/bridge.contract.json'), 'utf8'));
// The shell is in-repo at core/shells/ios since the PR-6 promotion, so the
// surfaces build is a sibling package: core/shells/ios -> core/packages/...
// The previous value pointed at a sibling `core-foundation` checkout, a layout
// that does not exist inside a worktree — the same stale-path class of bug that
// left the bridge drift gates silently SKIPping before promotion.
const defaultDist = resolve(root, '../../packages/surfaces/dist');
const dist = resolve(process.env.SURFACES_DIST ?? defaultDist);
const out = join(root, 'app/assets/surfaces');

if (!existsSync(join(dist, 'index.html'))) {
  console.error(
    `surfaces dist missing at ${dist} — run: cd core && pnpm --filter @omi-core/surfaces build`,
  );
  process.exit(1);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(dist, out, { recursive: true });

function stripMaps(dir) {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) stripMaps(p);
    else if (ent.name.endsWith('.map')) unlinkSync(p);
  }
}
stripMaps(out);

writeFileSync(
  join(out, 'manifest.json'),
  JSON.stringify(
    { bundleId: 'surfaces', bridgeContractVersion: contract.version, source: 'core:packages/surfaces/dist' },
    null,
    2,
  ),
);

console.log(`surfaces bundle -> ${out} (contract ${contract.version}, from ${dist})`);

// The native consumer-evidence writer reads this separately from the copied
// surfaces-dist stamp. Neither hash is accepted from JavaScript or launcher
// arguments, and the two artifacts remain independently attributable.
try {
  const { worktreeStamp, writeStampFile } = await import('../../../../integration/lib/provenance.mjs');
  writeStampFile(
    join(out, 'omi-ios-shell-build-stamp.json'),
    worktreeStamp({ repo: 'core-foundation', artifact: 'ios-bundle' }),
  );
} catch (error) {
  writeFileSync(
    join(out, 'omi-ios-shell-build-stamp.json'),
    `${JSON.stringify({
      schema: 1,
      repo: 'core-foundation',
      artifact: 'ios-bundle',
      unavailable: error instanceof Error ? error.message : String(error),
    }, null, 2)}\n`,
  );
}
