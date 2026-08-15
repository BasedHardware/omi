import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const LAB_ORIGIN = "http://127.0.0.1:4650";
export const LAB_PLATFORMS = ["mobile", "desktop"];
export const LAB_LOCALES = ["en-US"];
export const LAB_VIEWPORTS = {
  mobile: { width: 390, height: 844 },
  desktop: { width: 1280, height: 800 },
};

const catalogPath = resolve(packageRoot, "src/lab/catalog.ts");

function quotedStrings(source, pattern) {
  const match = source.match(pattern);
  if (!match) return null;
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]);
}

function fixtureArray(source, name) {
  const values = quotedStrings(source, new RegExp(`export const ${name} = \\[([\\s\\S]*?)\\] as const`));
  if (!values) throw new Error(`missing fixture array ${name}`);
  return values;
}

function polishStates(source, domain) {
  const values = quotedStrings(source, new RegExp(`${domain}: \\[([^\\]]+)\\]`));
  if (!values) throw new Error(`missing polish domain ${domain}`);
  return values;
}

function resolveStates(expression, files) {
  if (expression.startsWith("POLISH_EVIDENCE_STATES.")) {
    return polishStates(files.polish, expression.slice("POLISH_EVIDENCE_STATES.".length));
  }
  const table = {
    MEMORY_STATES: () => fixtureArray(files.memories, "FIXTURE_STATES"),
    CONVERSATION_FIXTURE_STATES: () => fixtureArray(files.conversations, "CONVERSATION_FIXTURE_STATES"),
    TASK_STATES: () => fixtureArray(files.tasks, "FIXTURE_STATES"),
    PROPOSITION_FIXTURE_STATES: () => fixtureArray(files.propositions, "PROPOSITION_FIXTURE_STATES"),
    CHAT_FIXTURE_STATES: () => fixtureArray(files.chat, "CHAT_FIXTURE_STATES"),
    SETTINGS_FIXTURE_STATES: () => fixtureArray(files.settings, "SETTINGS_FIXTURE_STATES"),
  };
  const reader = table[expression];
  if (!reader) throw new Error(`unknown lab state source ${expression}`);
  return reader();
}

function parseSurfaceBlock(source, constName, files) {
  const match = source.match(new RegExp(`export const ${constName}[\\s\\S]*?= \\[([\\s\\S]*?)\\n\\];`));
  if (!match) throw new Error(`missing ${constName} in lab catalog`);
  const rows = [];
  const rowRe = /\{\s*id: "([^"]+)"[\s\S]*?states: ([A-Za-z0-9_.]+)(?:, polishDomain: "([^"]+)")?/g;
  for (const row of match[1].matchAll(rowRe)) {
    rows.push({
      id: row[1],
      states: resolveStates(row[2], files),
      polish: row[3] !== undefined,
    });
  }
  if (rows.length === 0) throw new Error(`${constName} parsed zero surfaces`);
  return rows;
}

function readCatalogFiles() {
  const src = resolve(packageRoot, "src/production");
  return {
    catalog: readFileSync(catalogPath, "utf8"),
    memories: readFileSync(resolve(src, "memory-fixtures.ts"), "utf8"),
    conversations: readFileSync(resolve(src, "conversation-fixtures.ts"), "utf8"),
    tasks: readFileSync(resolve(src, "task-fixtures.ts"), "utf8"),
    propositions: readFileSync(resolve(src, "proposition-fixtures.ts"), "utf8"),
    chat: readFileSync(resolve(src, "chat-fixtures.ts"), "utf8"),
    settings: readFileSync(resolve(src, "settings-fixtures.ts"), "utf8"),
    polish: readFileSync(resolve(src, "polish-evidence-fixtures.ts"), "utf8"),
  };
}

function fixturePath(surface, state, platform, locale, polish) {
  const params = new URLSearchParams({ qa: surface, state, platform, locale, ...(polish ? { polish: "1" } : {}) });
  return `?${params.toString()}`;
}

function shellReachability(platform) {
  if (platform === "mobile") {
    return {
      reachable: false,
      reason: "macOS fixture windows cannot be 390×844; GlassHost minimum width is 760px, so true mobile chrome is browser-only.",
    };
  }
  return { reachable: true, reason: null };
}

export function enumerateLabStates(origin = LAB_ORIGIN) {
  const files = readCatalogFiles();
  const byKey = new Map();
  const catalogs = [
    ["lab", parseSurfaceBlock(files.catalog, "SURFACES", files)],
    ["matrix", parseSurfaceBlock(files.catalog, "MATRIX_SURFACES", files)],
  ];
  for (const [catalog, surfaces] of catalogs) {
    for (const surface of surfaces) {
      for (const state of surface.states) {
        for (const platform of LAB_PLATFORMS) {
          for (const locale of LAB_LOCALES) {
            const path = fixturePath(surface.id, state, platform, locale, surface.polish);
            const existing = byKey.get(path);
            if (existing) {
              if (!existing.catalogs.includes(catalog)) existing.catalogs.push(catalog);
              continue;
            }
            const id = `${surface.id}.${state}.${platform}.${locale}.${surface.polish ? "polish" : "raw"}`;
            byKey.set(path, {
              id,
              url: `${origin}/${path}`,
              path,
              surface: surface.id,
              state,
              platform,
              locale,
              polish: surface.polish,
              catalogs: [catalog],
              viewport: LAB_VIEWPORTS[platform],
              shell: shellReachability(platform),
            });
          }
        }
      }
    }
  }
  return [...byKey.values()].sort((left, right) => left.id.localeCompare(right.id));
}

export function generateManifest(origin = LAB_ORIGIN) {
  const states = enumerateLabStates(origin);
  return {
    schema: "omi.ui-harness.manifest/v1",
    origin,
    platforms: LAB_PLATFORMS,
    locales: LAB_LOCALES,
    viewports: LAB_VIEWPORTS,
    count: states.length,
    states,
  };
}

export async function withLabPreview(callback) {
  const dist = resolve(packageRoot, "dist/index.html");
  if (!existsSync(dist)) {
    throw new Error("surfaces dist missing; run: cd frontend && pnpm --filter @omi-core/surfaces build");
  }
  const { preview } = await import("vite");
  const server = await preview({
    root: packageRoot,
    configFile: resolve(packageRoot, "vite.config.ts"),
    logLevel: "error",
    preview: { host: "127.0.0.1", port: 0, strictPort: false },
  });
  try {
    return await callback(server);
  } finally {
    await server.close();
  }
}

export function viteOrigin(server) {
  const url = server.resolvedUrls?.local?.[0];
  if (!url) throw new Error("vite did not bind a loopback origin");
  return url.replace(/\/$/, "");
}
