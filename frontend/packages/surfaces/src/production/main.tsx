import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { t } from "@omi-core/i18n";
import { getTheme, themeNameFor, type ColorMode, type ThemeName } from "@omi-core/tokens";
import { realEnv } from "@omi-core/kernel";
import { bridgeHttpClient, isBridgeHttpAvailable, openWebStorageBridge } from "@omi-core/bridge-web";
import { createLegacyProductionStoreFactory } from "./ProductionStores.js";
import { MemoriesProduction } from "./MemoriesProduction.js";
import { ConversationsProduction } from "./ConversationsProduction.js";
import { TasksProduction, type TasksProductionProps } from "./TasksProduction.js";
import { HomeProduction } from "./HomeProduction.js";
import { MemoriesPlatformProduction } from "./MemoriesPlatformProduction.js";
import { fixtureStore, FIXTURE_STATES, type FixtureState } from "./memory-fixtures.js";
import { PROPOSITION_FIXTURE_STATES, fixturePropositionStore, type PropositionFixtureState } from "./proposition-fixtures.js";
import { CONVERSATION_FIXTURE_STATES, fixtureConversationDetailId, fixtureConversationStore, fixtureFolderStore, type ConversationFixtureState } from "./conversation-fixtures.js";
import { FIXED_NOW as TASK_FIXED_NOW, FIXTURE_STATES as TASK_FIXTURE_STATES, fixtureStore as fixtureTaskStore, type FixtureState as TaskFixtureState } from "./task-fixtures.js";
import "./styles.css";

const query = new URLSearchParams(location.search);
const requestedRoute = query.get("route");
const requestedQa = query.get("qa");
// The platform generation is a second *presentation* of Memories, not a second route:
// `?qa=memories-platform` reviews it against fixtures, and generation selection for the
// live path is FE-CORE's `resolveGenerationSelection`, never a URL guess.
const route: "home" | "memories" | "conversations" | "tasks" = requestedRoute === "tasks" || requestedQa === "tasks"
  ? "tasks"
  : requestedRoute === "conversations" || requestedQa === "conversations" || requestedQa === "conversation-detail"
    ? "conversations"
    : requestedRoute === "memories" || requestedQa === "memories" || requestedQa === "memories-platform"
      ? "memories"
      : "home";
const requestedPlatform = query.get("platform");
const platform: "mobile" | "desktop" = requestedPlatform === "desktop" || requestedPlatform === "mobile"
  ? requestedPlatform
  : matchMedia("(min-width: 760px)").matches ? "desktop" : "mobile";
type ThemeSelection = "default" | "system" | ColorMode;
const requestedTheme = query.get("theme");
const themeSelection: ThemeSelection = requestedTheme === "dark" || requestedTheme === "light" || requestedTheme === "system"
  ? requestedTheme
  : "default";
const systemPrefersDark = matchMedia("(prefers-color-scheme: dark)");
const colorModeFor = (selection: ThemeSelection): ColorMode => selection === "system"
  ? systemPrefersDark.matches ? "dark" : "light"
  : selection === "dark" || selection === "light"
    ? selection
    : platform === "mobile" ? "dark" : "light";
let themeName: ThemeName = themeNameFor(platform, colorModeFor(themeSelection));
const locale = query.get("locale")?.trim() || navigator.language || "en";
const translateTasks = t.bind(null, locale) as unknown as TasksProductionProps["translate"];
document.title = t(locale, "app.name");
const rootStyle = document.documentElement.style;
const set = (name: string, value: string | number): void => rootStyle.setProperty(name, String(value));

document.documentElement.dataset["platform"] = platform;
document.documentElement.dataset["themeSelection"] = themeSelection;
const applyTheme = (name: ThemeName): void => {
  const theme = getTheme(name);
  const colorMode: ColorMode = name === "mobileDark" || name === "desktopDarkGlass" ? "dark" : "light";
  themeName = name;
  document.documentElement.dataset["theme"] = name;
  document.documentElement.dataset["colorMode"] = colorMode;
  // The prototype AppKit host is Aqua-pinned. Explicit desktop dark mode must
  // paint its own fallback instead of claiming that light native material is dark.
  document.documentElement.dataset["nativeGlass"] = query.get("nativeGlass") === "1" && name === "desktopLightGlass" ? "true" : "false";
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
  for (const [token, value] of Object.entries(theme.radii)) set(`--radius-${token}`, `${value}px`);
  for (const [token, value] of Object.entries(theme.spacing)) set(`--space-${token}`, `${value}px`);
  for (const [token, role] of Object.entries(theme.typography)) {
    set(`--type-${token}-size`, `${role.size}px`);
    set(`--type-${token}-weight`, role.weight);
    set(`--type-${token}-line`, role.lineHeight);
    set(`--type-${token}-tracking`, `${role.tracking}px`);
    set(`--type-${token}-family`, role.family === "openRunde" ? "Open Runde, system-ui" : "system-ui");
  }
};
applyTheme(themeName);
if (themeSelection === "system") {
  systemPrefersDark.addEventListener("change", () => applyTheme(themeNameFor(platform, colorModeFor("system"))));
}

let readyLogged = false;
const emitReady = (state: string): void => {
  if (readyLogged) return;
  readyLogged = true;
  console.info(`OMI_PRODUCTION_READY route=${route} state=${state}`);
};

function bridgeUnavailable(): React.JSX.Element {
  return (
    <main className="bridge-unavailable" data-production-shell="true" data-route={route} data-surface-state="bridge-unavailable" data-qa-fixture="none">
      <h1>{t(locale, "app.name")}</h1>
      <p>{t(locale, "qa.bridgeUnavailable")}</p>
      <a href="?rig=dev">{t(locale, "qa.rig")}</a>
    </main>
  );
}

if (query.get("lab") === "1") {
  void import("../lab/main.js");
} else if (query.get("rig") === "dev") {
  void import("../dev/main.js");
} else {
  const fixtureValue = query.get("state");
  const memoryFixture = requestedQa === "memories" && FIXTURE_STATES.includes(fixtureValue as FixtureState)
    ? fixtureValue as FixtureState
    : undefined;
  const conversationFixture = (requestedQa === "conversations" || requestedQa === "conversation-detail") && CONVERSATION_FIXTURE_STATES.includes(fixtureValue as ConversationFixtureState)
    ? fixtureValue as ConversationFixtureState
    : undefined;
  const taskFixture = requestedQa === "tasks" && TASK_FIXTURE_STATES.includes(fixtureValue as TaskFixtureState)
    ? fixtureValue as TaskFixtureState
    : undefined;
  const detailId = query.get("conversation") ?? (requestedQa === "conversation-detail" && conversationFixture ? fixtureConversationDetailId(conversationFixture) : undefined);
  const propositionFixture = requestedQa === "memories-platform" && PROPOSITION_FIXTURE_STATES.includes(fixtureValue as PropositionFixtureState)
    ? fixtureValue as PropositionFixtureState
    : undefined;
  const homeFixture = requestedQa === "home";
  const root = createRoot(document.getElementById("root")!);
  if (propositionFixture) {
    // `source` is required by the component, so a fixture render can never be mistaken
    // for live account data — the badge is on screen at every width.
    root.render(<StrictMode><MemoriesPlatformProduction store={fixturePropositionStore(propositionFixture)} source={{ kind: "fixture", fixture: propositionFixture }} locale={locale} onReady={() => emitReady(`fixture:${propositionFixture}`)} /></StrictMode>);
  } else if (homeFixture) {
    root.render(<StrictMode><HomeProduction sources={{ memories: fixtureStore("normal"), conversations: fixtureConversationStore("normal") }} locale={locale} onReady={() => emitReady("fixture:home")} /></StrictMode>);
  } else if (taskFixture) {
    root.render(<StrictMode><TasksProduction store={fixtureTaskStore(taskFixture)} fixture={taskFixture} locale={locale} translate={translateTasks} now={TASK_FIXED_NOW} onReady={() => emitReady(`fixture:${taskFixture}`)} /></StrictMode>);
  } else if (conversationFixture) {
    root.render(<StrictMode><ConversationsProduction store={fixtureConversationStore(conversationFixture, requestedQa === "conversation-detail")} foldersStore={fixtureFolderStore()} fixture={conversationFixture} detailId={detailId} locale={locale} onReady={() => emitReady(`fixture:${conversationFixture}`)} /></StrictMode>);
  } else if (memoryFixture) {
    root.render(<StrictMode><MemoriesProduction store={fixtureStore(memoryFixture)} fixture={memoryFixture} locale={locale} onReady={() => emitReady(`fixture:${memoryFixture}`)} /></StrictMode>);
  } else if (!isBridgeHttpAvailable()) {
    root.render(<StrictMode>{bridgeUnavailable()}</StrictMode>);
    emitReady("bridge-unavailable");
  } else {
    const profile = query.get("profile")?.trim() || "default";
    void (async () => {
      try {
        const bridge = await openWebStorageBridge(profile);
        const http = bridgeHttpClient();
        const env = realEnv();
        const stores = createLegacyProductionStoreFactory(bridge, env, http);
        if (route === "home") {
          const [memories, conversations] = await Promise.all([
            stores.openMemories(),
            stores.openConversations(),
          ]);
          await Promise.allSettled([memories.refresh(), conversations.refresh()]);
          root.render(<StrictMode><HomeProduction sources={{ memories, conversations }} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else if (route === "tasks") {
          const store = await stores.openTasks();
          root.render(<StrictMode><TasksProduction store={store} locale={locale} translate={translateTasks} now={env.now()} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else if (route === "conversations") {
          const [store, foldersStore] = await Promise.all([
            stores.openConversations(),
            stores.openFolders(),
          ]);
          root.render(<StrictMode><ConversationsProduction store={store} foldersStore={foldersStore} detailId={detailId} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else {
          const store = await stores.openMemories();
          root.render(<StrictMode><MemoriesProduction store={store} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        }
      } catch {
        root.render(<StrictMode>{bridgeUnavailable()}</StrictMode>);
        emitReady("bridge-unavailable");
      }
    })();
  }
}
