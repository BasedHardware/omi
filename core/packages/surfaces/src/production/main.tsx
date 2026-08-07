import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { t } from "@omi-core/i18n";
import { getTheme, type ThemeName } from "@omi-core/tokens";
import { realEnv } from "@omi-core/kernel";
import { bridgeHttpClient, isBridgeHttpAvailable, openWebStorageBridge } from "@omi-core/bridge-web";
import { MemoriesStore } from "@omi-core/domain";
import { MemoriesProduction } from "./MemoriesProduction.js";
import { fixtureStore, FIXTURE_STATES, type FixtureState } from "./memory-fixtures.js";
import "./styles.css";

const query = new URLSearchParams(location.search);
const requestedPlatform = query.get("platform");
const platform: "mobile" | "desktop" = requestedPlatform === "desktop" || requestedPlatform === "mobile"
  ? requestedPlatform
  : matchMedia("(min-width: 760px)").matches ? "desktop" : "mobile";
const themeName: ThemeName = platform === "desktop" ? "desktopLightGlass" : "mobileDark";
const theme = getTheme(themeName);
const locale = query.get("locale")?.trim() || navigator.language || "en";
document.title = t(locale, "app.name");
const rootStyle = document.documentElement.style;
const set = (name: string, value: string | number): void => rootStyle.setProperty(name, String(value));

document.documentElement.dataset["platform"] = platform;
document.documentElement.dataset["theme"] = themeName;
set("--surface-canvas", theme.colors.surface.canvas);
set("--surface-raised", theme.colors.surface.raised);
set("--surface-elevated", theme.colors.surface.elevated);
set("--surface-scrim", theme.colors.surface.scrim);
set("--content-primary", theme.colors.content.primary);
set("--content-secondary", theme.colors.content.secondary);
set("--content-tertiary", theme.colors.content.tertiary);
set("--content-inverse", theme.colors.content.inverse);
set("--border", theme.colors.border);
set("--focus", theme.colors.focus);
set("--danger", theme.colors.danger);
set("--success", theme.colors.success);
set("--warning", theme.colors.warning);
set("--accent", theme.colors.accent);
set("--min-tap-target", `${theme.interaction.minTapTarget}px`);
set("--focus-ring-width", `${theme.interaction.focusRingWidth}px`);
for (const [name, value] of Object.entries(theme.radii)) set(`--radius-${name}`, `${value}px`);
for (const [name, value] of Object.entries(theme.spacing)) set(`--space-${name}`, `${value}px`);
for (const [name, role] of Object.entries(theme.typography)) {
  set(`--type-${name}-size`, `${role.size}px`);
  set(`--type-${name}-weight`, role.weight);
  set(`--type-${name}-line`, role.lineHeight);
  set(`--type-${name}-tracking`, `${role.tracking}px`);
  set(`--type-${name}-family`, role.family === "openRunde" ? "Open Runde, system-ui" : "system-ui");
}

let readyLogged = false;
const emitReady = (state: string): void => {
  if (readyLogged) return;
  readyLogged = true;
  console.info(`OMI_PRODUCTION_READY route=memories state=${state}`);
};

function bridgeUnavailable(): React.JSX.Element {
  return (
    <main className="bridge-unavailable" data-production-shell="true" data-route="memories" data-surface-state="bridge-unavailable" data-qa-fixture="none">
      <h1>{t(locale, "app.name")}</h1>
      <p>{t(locale, "qa.bridgeUnavailable")}</p>
      <a href="?rig=dev">{t(locale, "qa.rig")}</a>
    </main>
  );
}

if (query.get("rig") === "dev") {
  void import("../dev/main.js");
} else {
  const fixtureValue = query.get("qa") === "memories" ? query.get("state") : null;
  const fixture = FIXTURE_STATES.includes(fixtureValue as FixtureState) ? fixtureValue as FixtureState : undefined;
  const root = createRoot(document.getElementById("root")!);
  if (fixture) {
    root.render(<StrictMode><MemoriesProduction store={fixtureStore(fixture)} fixture={fixture} locale={locale} onReady={() => emitReady(`fixture:${fixture}`)} /></StrictMode>);
  } else if (!isBridgeHttpAvailable()) {
    root.render(<StrictMode>{bridgeUnavailable()}</StrictMode>);
    emitReady("bridge-unavailable");
  } else {
    const profile = query.get("profile")?.trim() || "default";
    void (async () => {
      try {
        const bridge = await openWebStorageBridge(profile);
        const store = await MemoriesStore.open(bridge, realEnv(), bridgeHttpClient());
        root.render(<StrictMode><MemoriesProduction store={store} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
      } catch {
        root.render(<StrictMode>{bridgeUnavailable()}</StrictMode>);
        emitReady("bridge-unavailable");
      }
    })();
  }
}
