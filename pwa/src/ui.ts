import type { BrowserCapabilitySnapshot } from "./browser-adapters";
import type { BrowserCurrent } from "./data";

export type AppViewState = {
  currents: readonly BrowserCurrent[];
  dataMode: "demo" | "backend";
  dataStatus: "demo" | "loading" | "ready" | "unavailable";
  unavailable: readonly string[];
  searchQuery: string;
  capability: BrowserCapabilitySnapshot;
  capabilityNotice: string | null;
  installAvailable: boolean;
};

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "'": "&#39;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
    };
    return entities[character];
  });
}

function icon(path: string): string {
  return `<svg aria-hidden="true" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${path}" /></svg>`;
}

function formatDate(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
  }).format(timestamp);
}

function currentCard(item: BrowserCurrent): string {
  return `<article class="current-card current-${item.kind}">
    <div class="current-card-top"><span class="current-kind">${escapeHtml(
      item.kind
    )}</span><span class="current-date">${escapeHtml(
    formatDate(item.updatedAt)
  )}</span></div>
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.summary)}</p>
    <span class="current-source">${escapeHtml(item.source)}</span>
  </article>`;
}

function bluetoothCopy(capability: BrowserCapabilitySnapshot): {
  label: string;
  detail: string;
  action: string;
  disabled: boolean;
} {
  if (capability.bluetooth === "unsupported") {
    return {
      label: "Unavailable in this browser",
      detail: "Web Bluetooth is not exposed here. No pendant is assumed.",
      action: "Bluetooth unavailable",
      disabled: true,
    };
  }
  if (capability.bluetooth === "selected") {
    return {
      label:
        capability.bluetoothDeviceName === null
          ? "Device selected"
          : `Selected · ${capability.bluetoothDeviceName}`,
      detail:
        "A browser device was selected; Omi identity and connection are not verified.",
      action: "Choose another device",
      disabled: false,
    };
  }
  if (capability.bluetooth === "denied") {
    return {
      label: "Permission denied",
      detail: "The browser did not grant Bluetooth chooser access.",
      action: "Try Bluetooth again",
      disabled: false,
    };
  }
  if (capability.bluetooth === "error") {
    return {
      label: "Browser check failed",
      detail: "The browser Bluetooth chooser returned an error.",
      action: "Try Bluetooth again",
      disabled: false,
    };
  }
  return {
    label: "Available · no device selected",
    detail:
      "The browser exposes Web Bluetooth, but no Omi device is connected.",
    action: "Choose Bluetooth device",
    disabled: false,
  };
}

function microphoneCopy(capability: BrowserCapabilitySnapshot): {
  label: string;
  detail: string;
  action: string;
  disabled: boolean;
} {
  if (capability.microphone === "unsupported") {
    return {
      label: "Unavailable in this browser",
      detail: "No microphone capture API is exposed.",
      action: "Microphone unavailable",
      disabled: true,
    };
  }
  if (capability.microphone === "granted") {
    return {
      label: "Permission granted",
      detail:
        "A short browser microphone probe passed and its stream was stopped.",
      action: "Check again",
      disabled: false,
    };
  }
  if (capability.microphone === "denied") {
    return {
      label: "Permission denied",
      detail: "The browser did not grant microphone access.",
      action: "Check microphone again",
      disabled: false,
    };
  }
  if (capability.microphone === "error") {
    return {
      label: "Browser check failed",
      detail: "The microphone probe returned an error.",
      action: "Check microphone again",
      disabled: false,
    };
  }
  return {
    label: "Available · permission not requested",
    detail:
      "The browser can probe a microphone. Omi capture is not wired into this surface.",
    action: "Check microphone",
    disabled: false,
  };
}

function searchResults(state: AppViewState): string {
  const query = state.searchQuery.trim();
  if (query.length === 0) return "";
  const normalized = query.toLocaleLowerCase();
  const results = state.currents.filter((item) =>
    `${item.kind}\n${item.title}\n${item.summary}`
      .toLocaleLowerCase()
      .includes(normalized)
  );
  return `<section class="search-results" aria-label="Search results" data-search-results>
    <div class="section-heading search-heading"><div><span class="eyebrow">SEARCH / ${escapeHtml(
      query
    )}</span><h2>Results</h2></div><button class="text-button" data-action="clear-search">Clear ${icon(
    "M18 6 6 18M6 6l12 12"
  )}</button></div>
    ${
      results.length > 0
        ? `<div class="results-grid">${results.map(currentCard).join("")}</div>`
        : '<div class="empty-state"><span class="empty-mark">0</span><div><strong>No results yet</strong><p>Try a word from a current, memory, or task.</p></div></div>'
    }
  </section>`;
}

export function renderApp(state: AppViewState): string {
  const bluetooth = bluetoothCopy(state.capability);
  const microphone = microphoneCopy(state.capability);
  const currentSource =
    state.dataMode === "demo"
      ? "Local validation data"
      : state.dataStatus === "loading"
      ? "Reading backend"
      : "Credential-free backend read";
  const currentContent =
    state.dataStatus === "loading"
      ? '<div class="loading-state"><span class="loading-dot"></span><span>Reading Currents from the configured origin…</span></div>'
      : state.currents.length > 0
      ? `<div class="currents-grid">${state.currents
          .slice(0, 3)
          .map(currentCard)
          .join("")}</div>`
      : '<div class="empty-state"><span class="empty-mark">—</span><div><strong>No currents available</strong><p>This surface has no authenticated backend session, so it will not invent saved data.</p></div></div>';
  const unavailable =
    state.unavailable.length > 0
      ? `<p class="data-note">Unavailable reads: ${escapeHtml(
          state.unavailable.join(", ")
        )}. Nothing was substituted.</p>`
      : "";
  const notice =
    state.capabilityNotice === null
      ? ""
      : `<div class="notice" role="status">${escapeHtml(
          state.capabilityNotice
        )}</div>`;

  return `<div class="app-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Omi v5 browser validation home"><span class="brand-mark"><span></span></span><span><span class="eyebrow">OMI / V5</span><strong>Browser validation</strong></span></a>
      <div class="topbar-actions"><span class="local-chip"><span class="pulse"></span> Local surface</span>${
        state.installAvailable
          ? '<button class="install-button" data-action="install">Install app</button>'
          : ""
      }</div>
    </header>
    <main class="page" aria-label="Omi Home">
      <section class="hero-grid" aria-label="Omi pendant status">
        <div class="hero-copy">
          <span class="eyebrow">HOME / PRESENT MOMENT</span>
          <h1>Make room for<br /><em>what matters now.</em></h1>
          <p class="hero-lede">A low-friction browser surface for validating Omi’s Home contract before it moves back into React Native.</p>
          <p class="honesty"><span class="honesty-dot"></span> Browser state is observed only. No Omi device or permission is assumed.</p>
        </div>
        <div class="pendant-card">
          <div class="pendant-ambient"></div><div class="pendant-orbit orbit-one"></div><div class="pendant-orbit orbit-two"></div>
          <div class="pendant" role="img" aria-label="Omi pendant"><span class="pendant-loop"></span><span class="pendant-face"><i></i><i></i><b></b></span></div>
          <div class="pendant-caption"><span class="eyebrow">PENDANT / STATUS</span><strong>${
            bluetooth.label
          }</strong><span>${bluetooth.detail}</span></div>
        </div>
      </section>
      <section class="signal-strip" aria-label="Browser capability and device state">
        <div class="signal-card"><div class="signal-icon">${icon(
          "M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4"
        )}</div><div><span class="eyebrow">BLUETOOTH</span><strong>${escapeHtml(
    bluetooth.label
  )}</strong><p>${escapeHtml(
    bluetooth.detail
  )}</p></div><button class="signal-action" data-action="bluetooth"${
    bluetooth.disabled ? " disabled" : ""
  }>${escapeHtml(bluetooth.action)}${icon(
    "M5 12h14M13 6l6 6-6 6"
  )}</button></div>
        <div class="signal-card"><div class="signal-icon">${icon(
          "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3ZM5 11a7 7 0 0 0 14 0M12 18v4M8 22h8"
        )}</div><div><span class="eyebrow">BROWSER CAPTURE</span><strong>${escapeHtml(
    microphone.label
  )}</strong><p>${escapeHtml(
    microphone.detail
  )}</p></div><button class="signal-action" data-action="microphone"${
    microphone.disabled ? " disabled" : ""
  }>${escapeHtml(microphone.action)}${icon(
    "M5 12h14M13 6l6 6-6 6"
  )}</button></div>
      </section>
      ${notice}
      <section class="currents-section" aria-label="Home currents">
        <div class="section-heading"><div><span class="eyebrow">HOME / NOW</span><h2>Currents</h2></div><span class="source-pill">${escapeHtml(
          currentSource
        )}</span></div>
        ${currentContent}${unavailable}
      </section>
      ${searchResults(state)}
    </main>
    <nav class="search-dock" aria-label="Search Omi dock"><form data-search-form><div class="search-symbol">${icon(
      "m11 19a8 8 0 1 1 5.7-2.3L21 21"
    )}</div><input aria-label="Search Omi" autocomplete="off" placeholder="Search Omi" value="${escapeHtml(
    state.searchQuery
  )}" data-search-input /><kbd>⌘ K</kbd>${
    state.searchQuery.trim().length > 0
      ? '<button class="clear-search" type="button" data-action="clear-search" aria-label="Clear search">×</button>'
      : ""
  }<button class="search-submit" type="submit" aria-label="Search Omi">${icon(
    "M5 12h14M13 6l6 6-6 6"
  )}</button></form><span class="dock-caption">Search your loaded conversations, memories, and tasks</span></nav>
  </div>`;
}
