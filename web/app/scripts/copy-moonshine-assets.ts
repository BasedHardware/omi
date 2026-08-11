import { cp, mkdir } from 'node:fs/promises';
import { categoryMetadata } from '../src/components/marketplace/category';

export function deriveWebSocketBaseUrl(
  apiBaseUrl: string,
  webSocketBaseUrl = '',
): string {
  if (webSocketBaseUrl) return webSocketBaseUrl;
  if (!apiBaseUrl) return '';
  const url = new URL(apiBaseUrl);
  url.protocol = url.protocol === 'http:' ? 'ws:' : 'wss:';
  return url.origin;
}

export function buildPublicEnvironment(
  environment: NodeJS.ProcessEnv,
): Record<string, string> {
  const apiBaseUrl = environment.NEXT_PUBLIC_API_BASE_URL ?? '';
  const webSocketBaseUrl = deriveWebSocketBaseUrl(
    apiBaseUrl,
    environment.NEXT_PUBLIC_WS_BASE_URL,
  );
  const publicEnvironment = Object.fromEntries(
    [
      'NEXT_PUBLIC_API_BASE_URL',
      'NEXT_PUBLIC_FIREBASE_API_KEY',
      'NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN',
      'NEXT_PUBLIC_FIREBASE_PROJECT_ID',
      'NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET',
      'NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID',
      'NEXT_PUBLIC_FIREBASE_APP_ID',
      'NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID',
      'NEXT_PUBLIC_FIREBASE_VAPID_KEY',
      'NEXT_PUBLIC_MIXPANEL_TOKEN',
    ].map((key) => [key, environment[key] ?? '']),
  );
  publicEnvironment.NEXT_PUBLIC_WS_BASE_URL = webSocketBaseUrl;
  return publicEnvironment;
}

async function buildAssets(): Promise<void> {
  await mkdir('.moonshine/public', { recursive: true });
  await cp('public', '.moonshine/public', { recursive: true, force: true });
  await cp('node_modules/leaflet/dist/leaflet.css', '.moonshine/public/leaflet.css');

  const publicEnvironment = buildPublicEnvironment(process.env);
  const clientPath = '.moonshine/public/client.js';
  const client = await Bun.file(clientPath).text();
  await Bun.write(
    clientPath,
    `globalThis.process = { env: ${JSON.stringify(publicEnvironment)} };\n${client}`,
  );

  const marketplaceCategories = Object.fromEntries(
    Object.entries(categoryMetadata).map(([id, metadata]) => [
      id,
      { displayName: metadata.displayName, description: metadata.description },
    ]),
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

const apiBaseInput = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';
const apiBaseUrl = apiBaseInput.endsWith('/') ? apiBaseInput.slice(0, -1) : apiBaseInput;
const marketplaceCategories = ${JSON.stringify(marketplaceCategories)};
const marketplaceDescription = 'Explore and install AI-powered apps for Omi. Enhance your experience with productivity tools, conversation insights, and more.';
let initialMarketplaceCache = { expiresAt: 0, apps: [] };
let marketplaceCache = { expiresAt: 0, apps: [] };

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
})[character]);

const formatCategoryName = (category) => String(category || 'other')
  .split('-')
  .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
  .join(' ');

async function getMarketplaceApps() {
  if (marketplaceCache.expiresAt > Date.now()) return marketplaceCache.apps;
  try {
      const response = await globalThis.fetch(apiBaseUrl + '/v1/approved-apps?include_reviews=true', {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) return [];
    const data = await response.json();
    const apps = Array.isArray(data) ? data : Array.isArray(data.plugins) ? data.plugins : [];
    marketplaceCache = { expiresAt: Date.now() + 60000, apps };
    return apps;
  } catch {
    return [];
  }
}

async function getInitialMarketplaceApps() {
  if (initialMarketplaceCache.expiresAt > Date.now()) return initialMarketplaceCache.apps;
  try {
    const response = await globalThis.fetch(apiBaseUrl + '/v2/apps?include_reviews=true', {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) return [];
    const data = await response.json();
    const apps = Array.from(new Map((data.groups || []).flatMap((group) => group.data || []).map((app) => [app.id, app])).values());
    initialMarketplaceCache = { expiresAt: Date.now() + 60000, apps };
    return apps;
  } catch {
    return [];
  }
}

function marketplaceList(apps, heading) {
  return '<section data-marketplace-server-content class="min-h-screen bg-[#0B0F17] px-6 py-16 text-white">' +
    '<h1 class="text-4xl font-bold">' + escapeHtml(heading) + '</h1>' +
    '<div class="mt-8 grid gap-4">' + apps.map((app) =>
      '<article><a href="/apps/' + encodeURIComponent(app.id) + '"><h2>' + escapeHtml(app.name) +
      '</h2><p>' + escapeHtml(app.description) + '</p></a></article>'
    ).join('') + '</div></section>';
}

async function marketplacePage(pathname) {
  if (pathname === '/apps') {
    const apps = await getInitialMarketplaceApps();
    return {
      title: 'Omi App Store - Discover AI-Powered Apps',
      description: marketplaceDescription,
      canonical: '/apps',
      image: '/og-apps.png',
      content: marketplaceList(apps, 'Omi App Store'),
    };
  }
  const pathParts = pathname.split('/').filter(Boolean);
  if (pathParts.length === 3 && pathParts[0] === 'apps' && pathParts[1] === 'category') {
    const category = decodeURIComponent(pathParts[2]);
    const categoryInfo = marketplaceCategories[category] || marketplaceCategories.other;
    const title = categoryInfo.displayName + ' Apps - Omi App Store';
    const description = categoryInfo.description + ' Browse ' + categoryInfo.displayName + ' apps for your Omi.';
    const apps = (await getInitialMarketplaceApps()).filter((app) => app.category === category);
    return {
      title,
      description,
      canonical: pathname,
      image: '/og-apps.png',
      content: marketplaceList(apps, categoryInfo.displayName + ' Apps'),
    };
  }
  if (pathParts.length === 2 && pathParts[0] === 'apps') {
    const id = decodeURIComponent(pathParts[1]);
    const app = (await getMarketplaceApps()).find((candidate) => candidate.id === id);
    if (!app) {
      return {
        title: 'App Not Found',
        description: 'The requested app could not be found.',
        canonical: pathname,
        content: '<main data-marketplace-server-content><h1>App not found</h1></main>',
      };
    }
    const categoryName = formatCategoryName(app.category);
    return {
      title: app.name + ' - ' + categoryName + ' App',
      description: app.description + ' Available on Omi, the AI-powered wearable platform.',
      socialDescription: app.description,
      canonical: pathname,
      image: app.image || '/og-apps.png',
      content: '<main data-marketplace-server-content class="min-h-screen bg-[#0B0F17] px-6 py-16 text-white"><article>' +
        '<h1 class="text-4xl font-bold">' + escapeHtml(app.name) + '</h1><p>by ' + escapeHtml(app.author) +
        '</p><p class="mt-8">' + escapeHtml(app.description) + '</p></article></main>',
    };
  }
  return undefined;
}

function injectServerContent(html, content) {
  if (!content) return html;
  const hostStart = html.indexOf('id="moonshine-app"');
  const hostEnd = hostStart === -1 ? -1 : html.indexOf('></div>', hostStart);
  if (hostEnd === -1) return html;
  return html.slice(0, hostEnd + 1) + content + html.slice(hostEnd + 1);
}

const renderer = {
  ...reactRenderer,
  async render(context) {
    const response = await reactRenderer.render(context);
    if (!response.headers.get('content-type')?.includes('text/html')) return response;
    const html = await response.text();
    const requestUrl = new URL(context.request.url);
    const pathname = requestUrl.pathname;
    const marketplace = await marketplacePage(pathname);
    const title = marketplace?.title ?? (pathname === '/login' ? 'Sign In to Omi' : 'Omi - Your AI Companion');
    const description = marketplace?.description ?? 'Omi - Your AI companion that turns thoughts into action.';
    const canonical = marketplace?.canonical ? requestUrl.origin + marketplace.canonical : undefined;
    const image = marketplace?.image ? new URL(marketplace.image, requestUrl.origin).href : undefined;
    const head = [
      '<meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">',
      '<title>' + escapeHtml(title) + '</title>',
      '<meta name="description" content="' + escapeHtml(description) + '">',
      canonical ? '<link rel="canonical" href="' + escapeHtml(canonical) + '">' : '',
      marketplace ? '<meta property="og:title" content="' + escapeHtml(title) + '">' : '',
      marketplace ? '<meta property="og:description" content="' + escapeHtml(marketplace.socialDescription || description) + '">' : '',
      canonical ? '<meta property="og:url" content="' + escapeHtml(canonical) + '">' : '',
      image ? '<meta property="og:image" content="' + escapeHtml(image) + '">' : '',
      marketplace ? '<meta name="twitter:card" content="summary_large_image">' : '',
      marketplace ? '<meta name="twitter:title" content="' + escapeHtml(title) + '">' : '',
      marketplace ? '<meta name="twitter:description" content="' + escapeHtml(marketplace.socialDescription || description) + '">' : '',
      image ? '<meta name="twitter:image" content="' + escapeHtml(image) + '">' : '',
      '<link rel="icon" href="/favicon.png">',
      '<link rel="stylesheet" href="/styles.css">',
      '<link rel="stylesheet" href="/leaflet.css">',
    ].join('');
    const headers = new Headers(response.headers);
    const body = injectServerContent(html, marketplace?.content);
    return new Response(body.replace('<head>', '<head>' + head), {
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
}

if (import.meta.main) await buildAssets();
