import { cp, mkdir } from 'node:fs/promises';

await mkdir('.moonshine/public', { recursive: true });
await cp('public', '.moonshine/public', { recursive: true, force: true });
await cp('node_modules/leaflet/dist/leaflet.css', '.moonshine/public/leaflet.css');

const publicEnvironment = Object.fromEntries(
  [
    'NEXT_PUBLIC_API_BASE_URL',
    'NEXT_PUBLIC_WS_BASE_URL',
    'NEXT_PUBLIC_FIREBASE_API_KEY',
    'NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN',
    'NEXT_PUBLIC_FIREBASE_PROJECT_ID',
    'NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET',
    'NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID',
    'NEXT_PUBLIC_FIREBASE_APP_ID',
    'NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID',
    'NEXT_PUBLIC_FIREBASE_VAPID_KEY',
    'NEXT_PUBLIC_MIXPANEL_TOKEN',
  ].map((key) => [key, process.env[key] ?? '']),
);
const clientPath = '.moonshine/public/client.js';
const client = await Bun.file(clientPath).text();
await Bun.write(
  clientPath,
  `globalThis.process = { env: ${JSON.stringify(publicEnvironment)} };\n${client}`,
);

const server = `import { createRequestHandler } from '@tschk/moonshine-server';
import { reactRenderer, registerRouteModules } from '@tschk/moonshine-react';
import { createBunServer } from '@tschk/moonshine-deploy-bun';
import { resolve } from 'node:path';
import manifest from './manifest.json' with { type: 'json' };
import { modules } from './dist/server.js';

const projectDir = resolve(import.meta.dir, '..');

// The renderer keeps its own route-module registry, separate from the modules
// the request pipeline receives, and nothing populates it for us. Without it the
// renderer falls back to \`await import(routeFile)\` — the route's SOURCE path —
// which the runtime image does not ship, so every server-rendered route 500s
// with "Cannot find module .../src/app/page.tsx". Only client-shell routes
// survive, which is why \`/\` broke while \`/login\` looked fine.
//
// The bundle keys those modules by their BUILD-TIME absolute paths, so handing
// them over as-is only works when the build and runtime directories happen to
// be identical. Re-key them against the manifest's relative route files and
// this runtime's own project directory.
// Every source-file key is rewritten from the build machine's root onto this
// one. Both consumers need it: the renderer's registry AND the request
// pipeline, which resolves layouts, middleware, and the page itself out of the
// same map.
const runtimeModules = {};
for (const [key, mod] of Object.entries(modules)) {
  const marker = key.lastIndexOf('/src/');
  runtimeModules[marker === -1 ? key : resolve(projectDir, key.slice(marker + 1))] = mod;
}
registerRouteModules(runtimeModules);
const abs = (path) => (path ? resolve(projectDir, path) : undefined);
const resolvedManifest = {
  ...manifest,
  routes: manifest.routes.map((route) => ({
    ...route,
    file: resolve(projectDir, route.file),
    dataFile: abs(route.dataFile),
    layouts: route.layouts?.map(abs).filter(Boolean),
    middleware: route.middleware?.map(abs).filter(Boolean),
    errorBoundary: abs(route.errorBoundary),
  })),
};

const titles = {
  '/login': 'Sign In to Omi',
  '/apps': 'Omi App Store - Discover AI-Powered Apps',
};

const renderer = {
  ...reactRenderer,
  async render(context) {
    const response = await reactRenderer.render(context);
    if (!response.headers.get('content-type')?.includes('text/html')) return response;
    const html = await response.text();
    const pathname = new URL(context.request.url).pathname;
    const title = titles[pathname] ?? 'Omi - Your AI Companion';
    const head = [
      '<meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">',
      '<title>' + title + '</title>',
      '<meta name="description" content="Omi - Your AI companion that turns thoughts into action.">',
      '<link rel="icon" href="/favicon.png">',
      '<link rel="stylesheet" href="/styles.css">',
      '<link rel="stylesheet" href="/leaflet.css">',
    ].join('');
    const headers = new Headers(response.headers);
    return new Response(html.replace('<head>', '<head>' + head), {
      status: response.status,
      headers,
    });
  },
};

const handler = createRequestHandler({
  manifest: resolvedManifest,
  modules: runtimeModules,
  renderer,
  staticDir: import.meta.dir + '/public',
});
// Prevent clickjacking: disallow embedding any page (incl. /login) in a frame.
const fetch = async (request) => {
  const response = await handler(request);
  const headers = new Headers(response.headers);
  headers.set('X-Frame-Options', 'DENY');
  headers.set('Content-Security-Policy', "frame-ancestors 'none'");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};
const server = createBunServer({
  fetch,
  port: Number(process.env.PORT) || 0,
  staticDir: import.meta.dir + '/public',
});
console.log(server.url.origin);
`;
await Bun.write('.moonshine/server.ts', server);
