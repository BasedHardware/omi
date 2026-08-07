/**
 * Dev server: full build, serve, rebuild on change.
 *
 * `moonshine dev` runs `moonshine build` and serves the result. That is not
 * enough here, because this app's runnable output is `moonshine build` plus
 * `build:assets`, which
 *
 *   - injects the NEXT_PUBLIC_* values into the client bundle (without them
 *     Firebase throws `auth/invalid-api-key` on boot and nothing mounts),
 *   - compiles Tailwind to `.moonshine/public/styles.css`,
 *   - copies `public/`, and
 *   - overwrites `.moonshine/server.ts` with the server that sets titles, head
 *     tags, and the clickjacking headers.
 *
 * `moonshine dev` also rewrites `.moonshine/` on every watch tick, so running
 * `build:assets` once beforehand does not survive the first rebuild. This runs
 * the whole pipeline instead, then restarts the real server.
 *
 * If moonshine grows a post-build hook, this file should go away and `dev`
 * should return to `moonshine dev`.
 */
import { watch } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dir, '..');
const watched = resolve(root, 'src');

let server: ReturnType<typeof Bun.spawn> | undefined;
let rebuildTimer: ReturnType<typeof setTimeout> | undefined;
let building = false;
let queued = false;

async function run(command: string[]): Promise<boolean> {
  const proc = Bun.spawn(command, {
    cwd: root,
    stdout: 'inherit',
    stderr: 'inherit',
  });
  return (await proc.exited) === 0;
}

async function stopServer(): Promise<void> {
  if (!server) return;
  server.kill();
  await server.exited;
  server = undefined;
}

async function buildAndServe(): Promise<void> {
  if (building) {
    queued = true;
    return;
  }
  building = true;

  try {
    await stopServer();
    // A failed build leaves the previous output in place; serving it again
    // would quietly show stale code, so stay down until the next save fixes it.
    if (!(await run(['bun', 'run', 'build']))) {
      console.error('Build failed — waiting for the next change.');
      return;
    }
    server = Bun.spawn(['bun', '.moonshine/server.ts'], {
      cwd: root,
      stdout: 'inherit',
      stderr: 'inherit',
      // Without a port the server picks a free one, so every rebuild moves the
      // origin and Firebase drops the signed-in session with it — you re-auth
      // after each save. Pin it; PORT still overrides.
      env: { PORT: '3000', ...process.env },
    });
  } finally {
    building = false;
    if (queued) {
      queued = false;
      void buildAndServe();
    }
  }
}

await buildAndServe();

const watcher = watch(watched, { recursive: true }, () => {
  if (rebuildTimer) clearTimeout(rebuildTimer);
  rebuildTimer = setTimeout(() => void buildAndServe(), 150);
});

async function shutdown(): Promise<void> {
  if (rebuildTimer) clearTimeout(rebuildTimer);
  watcher.close();
  await stopServer();
  process.exit(0);
}

process.on('SIGINT', () => void shutdown());
process.on('SIGTERM', () => void shutdown());
