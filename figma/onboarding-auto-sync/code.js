const DEFAULT_SOURCE_URL =
  "https://raw.githubusercontent.com/BasedHardware/omi/figma-onboarding-sync/onboarding/latest/manifest.json";
const DEFAULT_SECTION_NAME = "Onboarding Sync";
const DEFAULT_POLL_INTERVAL_MS = 15000;
const CONFIG_KEY = "omiOnboardingSyncConfig";
const CONTAINER_KEY = "omiOnboardingSyncContainer";

let syncInFlight = false;
let lastErrorSignature = "";

function loadConfig() {
  const stored = figma.root.getPluginData(CONFIG_KEY);

  if (stored) {
    try {
      return JSON.parse(stored);
    } catch (error) {
      console.error("Failed to parse onboarding sync config", error);
    }
  }

  return {
    sourceUrl: DEFAULT_SOURCE_URL,
    pollIntervalMs: DEFAULT_POLL_INTERVAL_MS,
    targetPageId: figma.currentPage.id,
    targetPageName: figma.currentPage.name,
    sectionName: DEFAULT_SECTION_NAME,
    lastAppliedSourceCommit: "",
  };
}

function saveConfig(config) {
  figma.root.setPluginData(CONFIG_KEY, JSON.stringify(config));
}

function resolveManifestUrl(sourceUrl) {
  const url = new URL(sourceUrl);
  url.searchParams.set("t", `${Date.now()}`);
  return url.toString();
}

async function fetchManifest(sourceUrl) {
  const response = await fetch(resolveManifestUrl(sourceUrl), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Manifest request failed with ${response.status}`);
  }
  return response.json();
}

async function fetchAssetBytes(url) {
  const response = await fetch(`${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Asset request failed with ${response.status} for ${url}`);
  }

  return new Uint8Array(await response.arrayBuffer());
}

function manifestSignature(manifest) {
  return manifest.sourceCommit || manifest.generatedAt || JSON.stringify(manifest.assets || []);
}

function findTargetPage(config) {
  if (config.targetPageId) {
    const byId = figma.root.children.find((page) => page.id === config.targetPageId);
    if (byId) {
      return byId;
    }
  }

  if (config.targetPageName) {
    const byName = figma.root.children.find((page) => page.name === config.targetPageName);
    if (byName) {
      config.targetPageId = byName.id;
      return byName;
    }
  }

  config.targetPageId = figma.currentPage.id;
  config.targetPageName = figma.currentPage.name;
  return figma.currentPage;
}

function ensureContainer(page, config, manifest) {
  let container = page.findOne(
    (node) => node.type === "FRAME" && node.getPluginData(CONTAINER_KEY) === "1"
  );

  if (!container) {
    container = figma.createFrame();
    container.name = config.sectionName;
    container.fills = [];
    container.strokes = [];
    container.clipsContent = false;
    container.setPluginData(CONTAINER_KEY, "1");
    container.x = figma.viewport.center.x - 1500;
    container.y = figma.viewport.center.y - 600;
    page.appendChild(container);
  }

  container.name = `${config.sectionName} · ${manifest.sourceCommit?.slice(0, 7) || "latest"}`;
  return container;
}

function clearChildren(node) {
  for (const child of [...node.children]) {
    child.remove();
  }
}

function createImageCard(asset, bytes) {
  const image = figma.createImage(bytes);
  const card = figma.createFrame();
  card.name = asset.name;
  card.resizeWithoutConstraints(asset.width, asset.height);
  card.fills = [];
  card.strokes = [];
  card.clipsContent = false;

  const rect = figma.createRectangle();
  rect.name = asset.name;
  rect.resizeWithoutConstraints(asset.width, asset.height);
  rect.fills = [
    {
      type: "IMAGE",
      scaleMode: "FILL",
      imageHash: image.hash,
    },
  ];

  card.appendChild(rect);
  return card;
}

async function applyManifest(config, manifest) {
  const page = findTargetPage(config);
  const container = ensureContainer(page, config, manifest);
  const assets = [];

  for (const asset of manifest.assets || []) {
    const assetUrl = new URL(asset.png, config.sourceUrl).toString();
    const bytes = await fetchAssetBytes(assetUrl);
    assets.push({ asset, bytes });
  }

  const origin = { x: container.x, y: container.y };
  clearChildren(container);

  const columns = 3;
  const gapX = 72;
  const gapY = 72;

  let maxWidth = 0;
  let maxHeight = 0;

  assets.forEach(({ asset, bytes }, index) => {
    const card = createImageCard(asset, bytes);
    const column = index % columns;
    const row = Math.floor(index / columns);
    card.x = column * (asset.width + gapX);
    card.y = row * (asset.height + gapY);
    container.appendChild(card);
    maxWidth = Math.max(maxWidth, card.x + asset.width);
    maxHeight = Math.max(maxHeight, card.y + asset.height);
  });

  container.resizeWithoutConstraints(Math.max(maxWidth, 1), Math.max(maxHeight, 1));
  container.x = origin.x;
  container.y = origin.y;

  config.lastAppliedSourceCommit = manifest.sourceCommit || manifest.generatedAt || "";
  saveConfig(config);
  figma.notify(`OMI onboarding synced${manifest.sourceCommit ? ` · ${manifest.sourceCommit.slice(0, 7)}` : ""}`, { timeout: 1800 });
}

async function syncOnce(force = false) {
  if (syncInFlight) {
    return;
  }

  syncInFlight = true;

  try {
    const config = loadConfig();
    const manifest = await fetchManifest(config.sourceUrl);
    const signature = manifestSignature(manifest);

    if (!force && signature === config.lastAppliedSourceCommit) {
      return;
    }

    await applyManifest(config, manifest);
    lastErrorSignature = "";
  } catch (error) {
    const signature = `${error}`;
    if (signature !== lastErrorSignature) {
      lastErrorSignature = signature;
      console.error("OMI onboarding sync failed", error);
      figma.notify(`OMI onboarding sync failed: ${error}`, { timeout: 3000 });
    }
  } finally {
    syncInFlight = false;
  }
}

figma.showUI(__html__, {
  visible: false,
  width: 240,
  height: 120,
  title: "OMI Onboarding Auto Sync",
});

figma.ui.onmessage = async (message) => {
  if (message.type === "tick") {
    await syncOnce(Boolean(message.force));
  }
};

saveConfig(loadConfig());
figma.ui.postMessage({
  type: "start",
  config: loadConfig(),
});
figma.notify("OMI onboarding auto-sync started", { timeout: 1500 });
