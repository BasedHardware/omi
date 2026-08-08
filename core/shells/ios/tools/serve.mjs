#!/usr/bin/env node
// Dev-mode surface server: serves surface/dist on :8787 with no-cache headers and
// rebuilds the bundle whenever surface/ sources change (live-reload loop for the
// surface without touching Dart). Ctrl-C to stop.
//   node tools/serve.mjs

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { watch } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dist = join(root, 'surface/dist');
const PORT = Number(process.env.PORT ?? 8787);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json' };

const rebuild = () => {
  try {
    execFileSync(process.execPath, [join(root, 'tools/build-surface.mjs')], { stdio: 'inherit' });
  } catch { /* keep serving the last good bundle */ }
};
rebuild();

for (const dir of ['surface/src', 'surface']) {
  watch(join(root, dir), { recursive: false }, (_e, f) => {
    if (f && /\.(ts|html)$/.test(f)) { console.log('change:', f); rebuild(); bumpStamp(); }
  });
}

let stamp = Date.now();
const bumpStamp = () => { stamp = Date.now(); };

createServer(async (req, res) => {
  const path = (req.url ?? '/').split('?')[0];
  if (path === '/stamp') {
    res.writeHead(200, { 'content-type': 'text/plain', 'cache-control': 'no-store' });
    res.end(String(stamp));
    return;
  }
  const file = join(dist, path === '/' ? 'index.html' : path.replace(/^\/+/, ''));
  try {
    const body = await readFile(file);
    res.writeHead(200, {
      'content-type': MIME[extname(file)] ?? 'application/octet-stream',
      'cache-control': 'no-store',
    });
    res.end(body);
  } catch {
    res.writeHead(404).end('not found');
  }
}).listen(PORT, () => console.log(`surface dev server: http://localhost:${PORT}`));
