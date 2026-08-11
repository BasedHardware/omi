import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { t } from "@omi-core/i18n";
import { getTheme, themeNameFor, type ColorMode, type ThemeName } from "@omi-core/tokens";
import { realEnv } from "@omi-core/kernel";
import { openOnDiskFallbackSink } from "@omi-core/sync";
import {
  bridgeChatAttachmentStagingPort,
  bridgeHttpClient,
  bridgeStreamPort,
  isBridgeHttpAvailable,
  openWebStorageBridge,
} from "@omi-core/bridge-web";
import {
  isSettingsAppearanceSelection,
  type SettingsAppearancePreference,
} from "@omi-core/contracts";
import {
  createPlatformListenCaptureClient,
  type PlatformListenSocketFactory,
} from "@omi-core/adapters-platform";
import type { SchemaDocument } from "@omi-core/wire-listen";
import { createPlatformProductionStoreFactory, parseGenerationSelectionFromEntries, resolveGenerationSelection } from "./ProductionStores.js";
import { createPlatformProductionListenStore } from "./createPlatformListenStore.js";
import { generationMismatch, resolveProductionRoute } from "./production-routing.js";
import { MemoriesProduction } from "./MemoriesProduction.js";
import { ConversationsProduction } from "./ConversationsProduction.js";
import { TasksProduction, type TasksProductionProps } from "./TasksProduction.js";
import { HomeProduction } from "./HomeProduction.js";
import { MemoriesPlatformProduction } from "./MemoriesPlatformProduction.js";
import { fixtureStore, FIXTURE_STATES, type FixtureState } from "./memory-fixtures.js";
import { PROPOSITION_FIXTURE_STATES, fixturePropositionStore, type PropositionFixtureState } from "./proposition-fixtures.js";
import { ChatProduction } from "./ChatProduction.js";
import { SettingsProduction } from "./SettingsProduction.js";
import { ListenProduction } from "./ListenProduction.js";
import { FoldersProduction } from "./FoldersProduction.js";
import { ProductionLifecycleRegion } from "./ProductionPrimitives.js";
import { createProductionListenHostSocketFactory } from "./listen-host-socket.js";
import { createPlatformProductionSettingsStore } from "./createPlatformSettingsStore.js";
import { CHAT_FIXTURE_STATES, fixtureChatStore, type ChatFixtureState } from "./chat-fixtures.js";
import { SETTINGS_FIXTURE_STATES, fixtureSettingsStore, type SettingsFixtureState } from "./settings-fixtures.js";
import { CONVERSATION_FIXTURE_STATES, fixtureConversationDetailId, fixtureConversationStore, fixtureFolderStore, type ConversationFixtureState } from "./conversation-fixtures.js";
import { FIXED_NOW as TASK_FIXED_NOW, FIXTURE_STATES as TASK_FIXTURE_STATES, fixtureStore as fixtureTaskStore, type FixtureState as TaskFixtureState } from "./task-fixtures.js";
import "./styles.css";

const query = new URLSearchParams(location.search);
const requestedRoute = query.get("route");
const requestedQa = query.get("qa");
/**
 * Host-supplied backend-generation selection, resolved BEFORE routing.
 *
 * "Host" means the launcher: a shell owns the WKWebView URL it loads AND may inject a
 * config object before the bundle runs. Both are the host speaking; neither is a user
 * typing a guess.
 *
 * Two things here were wrong and cost a night's headline result:
 *
 *  1. The query-param path hand-rolled `{ memories: "platform" }` instead of using
 *     `parseGenerationSelectionFromEntries`, which is the helper FE-CORE built for exactly
 *     this. It understands `generation=platform` as a BROADCAST preference that applies
 *     only to domains that actually have that generation, and reports a rejection when it
 *     does not — rather than silently asserting something about every domain.
 *  2. Selection was resolved after routing, so the route could not depend on it. It has to:
 *     a host that asks for the platform generation and lands on a surface that never reads
 *     it gets a perfect-looking app on the wrong generation and a served count of zero.
 */
type OmiHostConfig = {
  readonly generations?: unknown;
  readonly platformOriginLabel?: string;
  /** Native hosts attach auth while keeping credentials out of JS-visible state. */
  readonly listenSocketFactory?: PlatformListenSocketFactory;
};
const hostConfig: OmiHostConfig =
  (globalThis as { __OMI_HOST_CONFIG__?: OmiHostConfig }).__OMI_HOST_CONFIG__ ?? {};
const generationResolution = hostConfig.generations !== undefined
  ? resolveGenerationSelection(hostConfig.generations)
  : parseGenerationSelectionFromEntries(query.entries());
const generationSelection = generationResolution.selection;
const generationRejected = generationResolution.rejected;

// The platform generation is a second *presentation* of Memories, not a second route:
// `?qa=memories-platform` reviews it against fixtures, and generation selection for the
// live path is FE-CORE's `resolveGenerationSelection`, never a URL guess.
const route = resolveProductionRoute({
  requestedRoute,
  requestedQa,
  memoriesGeneration: generationSelection.memories,
});
const requestedPlatform = query.get("platform");
const platform: "mobile" | "desktop" = requestedPlatform === "desktop" || requestedPlatform === "mobile"
  ? requestedPlatform
  : matchMedia("(min-width: 760px)").matches ? "desktop" : "mobile";
const listenSource = platform;
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
const appearancePreference: SettingsAppearancePreference = {
  async readAppearance() {
    const value = localStorage.getItem("omi.settings.appearance.v1");
    return isSettingsAppearanceSelection(value) ? value : null;
  },
  async writeAppearance(value) {
    localStorage.setItem("omi.settings.appearance.v1", value);
  },
};
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

/**
 * What the app ACTUALLY did, readable from outside the bundle.
 *
 * A rejected selection and a silently-legacy render used to be indistinguishable from
 * outside the app — which is precisely how a served count of zero coexists with a
 * screenshot that looks perfect. `selected` is what the host asked for; `rendered` is what
 * was really constructed and put on screen. A script asserts on the second, never the
 * first.
 *
 * The shell reads this with `evaluateJavaScript`; log-scrapers read the same facts off the
 * OMI_PRODUCTION_READY line below.
 */
type OmiRuntimeState = {
  route: string;
  selected: typeof generationSelection;
  rejected: typeof generationRejected;
  rendered: { surface: string; memoriesGeneration: "legacy" | "platform" | null } | null;
  mismatch: string | null;
  // The artifact I measured is the artifact I edited: `__OMI_BUILD_STAMP__` is baked in
  // at build time (vite.config.ts's provenance plugin), so a shell or reviewer can read
  // this bundle's exact source tree without trusting a separate "when was this built"
  // claim. See integration/lib/provenance.mjs for what treeHash actually is.
  stamp: typeof __OMI_BUILD_STAMP__;
};
const runtimeState: OmiRuntimeState = {
  route,
  selected: generationSelection,
  rejected: generationRejected,
  rendered: null,
  mismatch: null,
  stamp: __OMI_BUILD_STAMP__,
};
(globalThis as { __OMI_RUNTIME_STATE__?: OmiRuntimeState }).__OMI_RUNTIME_STATE__ = runtimeState;
document.documentElement.dataset["generationMemories"] = generationSelection.memories;
if (generationRejected.length > 0) {
  document.documentElement.dataset["generationRejected"] = "true";
  console.warn(`OMI_GENERATION_REJECTED ${JSON.stringify(generationRejected)}`);
}
console.info(`OMI_GENERATION_SELECTION ${JSON.stringify(generationSelection)}`);

/** Records what really rendered, and shouts if it contradicts what was asked for. */
const markRendered = (
  surface: string,
  memoriesGeneration: "legacy" | "platform" | null,
): void => {
  runtimeState.rendered = { surface, memoriesGeneration };
  document.documentElement.dataset["renderedSurface"] = surface;
  if (memoriesGeneration === null) {
    delete document.documentElement.dataset["renderedMemoriesGeneration"];
  } else {
    document.documentElement.dataset["renderedMemoriesGeneration"] = memoriesGeneration;
  }
  if (generationMismatch(generationSelection.memories, memoriesGeneration)) {
    // The host asked for the platform generation and is being shown legacy memory records.
    // Never let this be quiet: it is a correct-looking app on the wrong backend.
    runtimeState.mismatch = `memories: selected platform, rendered legacy (surface ${surface})`;
    document.documentElement.dataset["generationMismatch"] = "true";
    console.error(`OMI_GENERATION_MISMATCH ${JSON.stringify(runtimeState.mismatch)}`);
  }
};

// `unavailable` on the stamp (git missing at build time, e.g. a tarball checkout) must
// read as visibly different from a real one here too — a log line that always has the
// same shape trains scrapers to stop looking at it.
const stampSummary = (stamp: typeof __OMI_BUILD_STAMP__): string =>
  "unavailable" in stamp ? "unavailable" : `${stamp.commit.slice(0, 12)}/${stamp.treeHash.slice(0, 12)}`;

let readyLogged = false;
const emitReady = (state: string): void => {
  if (readyLogged) return;
  readyLogged = true;
  const rendered = runtimeState.rendered;
  console.info(
    `OMI_PRODUCTION_READY route=${route} state=${state}`
    + ` generation.memories=${generationSelection.memories}`
    + ` rendered=${rendered ? rendered.surface : "none"}`
    + ` rendered.memories=${rendered?.memoriesGeneration ?? "none"}`
    + ` mismatch=${runtimeState.mismatch === null ? "no" : "yes"}`
    + ` stamp=${stampSummary(runtimeState.stamp)}`,
  );
};

export function bridgeUnavailable(): React.JSX.Element {
  const bridgeUnavailablePhase = "unavailable" as const;
  return (
    <main className="bridge-unavailable" data-production-shell="true" data-route={route} data-surface-state="bridge-unavailable" data-qa-fixture="none">
      <h1>{t(locale, "app.name")}</h1>
      <p>{t(locale, "qa.bridgeUnavailable")}</p>
      <ProductionLifecycleRegion
        phase={bridgeUnavailablePhase}
        hasSavedData={false}
        locale={locale}
        nextAction={t(locale, "qa.bridgeNext")}
      />
      <button type="button" className="bridge-unavailable-retry" onClick={() => window.location.reload()}>{t(locale, "common.retry")}</button>
    </main>
  );
}

function unsupportedRoute(): React.JSX.Element {
  return (
    <main className="bridge-unavailable" data-production-shell="true" data-route="unsupported" data-surface-state="unsupported" data-qa-fixture="none">
      <h1>{t(locale, "lifecycle.unavailable")}</h1>
      <p>{t(locale, "common.unknownError")}</p>
    </main>
  );
}

if (query.get("lab") === "1") {
  void import("../lab/main.js");
} else if (query.get("rig") === "dev") {
  void import("../dev/main.js");
} else {
  const fixtureValue = query.get("state");
  const fixtureRequest = requestedRoute === null;
  const memoryFixture = fixtureRequest && requestedQa === "memories" && FIXTURE_STATES.includes(fixtureValue as FixtureState)
    ? fixtureValue as FixtureState
    : undefined;
  const conversationFixture = fixtureRequest && (requestedQa === "conversations" || requestedQa === "conversation-detail") && CONVERSATION_FIXTURE_STATES.includes(fixtureValue as ConversationFixtureState)
    ? fixtureValue as ConversationFixtureState
    : undefined;
  const taskFixture = fixtureRequest && requestedQa === "tasks" && TASK_FIXTURE_STATES.includes(fixtureValue as TaskFixtureState)
    ? fixtureValue as TaskFixtureState
    : undefined;
  const detailId = query.get("conversation") ?? (requestedQa === "conversation-detail" && conversationFixture ? fixtureConversationDetailId(conversationFixture) : undefined);
  const propositionFixture = fixtureRequest && requestedQa === "memories-platform" && PROPOSITION_FIXTURE_STATES.includes(fixtureValue as PropositionFixtureState)
    ? fixtureValue as PropositionFixtureState
    : undefined;
  const chatFixture = fixtureRequest && requestedQa === "chat" && CHAT_FIXTURE_STATES.includes(fixtureValue as ChatFixtureState)
    ? fixtureValue as ChatFixtureState
    : undefined;
  const settingsFixture = fixtureRequest && requestedQa === "settings" && SETTINGS_FIXTURE_STATES.includes(fixtureValue as SettingsFixtureState)
    ? fixtureValue as SettingsFixtureState
    : undefined;
  const homeFixture = fixtureRequest && requestedQa === "home";
  const root = createRoot(document.getElementById("root")!);
  if (propositionFixture) {
    // `source` is required by the component, so a fixture render can never be mistaken
    // for live account data — the badge is on screen at every width.
    root.render(<StrictMode><MemoriesPlatformProduction store={fixturePropositionStore(propositionFixture)} source={{ kind: "fixture", fixture: propositionFixture }} locale={locale} onReady={() => emitReady(`fixture:${propositionFixture}`)} /></StrictMode>);
  } else if (chatFixture) {
    root.render(<StrictMode><ChatProduction store={fixtureChatStore(chatFixture)} fixture={chatFixture} locale={locale} onReady={() => emitReady(`fixture:${chatFixture}`)} /></StrictMode>);
  } else if (settingsFixture) {
    root.render(<StrictMode><SettingsProduction store={fixtureSettingsStore(settingsFixture)} fixture={settingsFixture} locale={locale} onReady={() => emitReady(`fixture:${settingsFixture}`)} /></StrictMode>);
  } else if (homeFixture) {
    root.render(<StrictMode><HomeProduction sources={{ memories: fixtureStore("normal"), conversations: fixtureConversationStore("normal") }} source={{ kind: "fixture", fixture: "home" }} locale={locale} onReady={() => emitReady("fixture:home")} /></StrictMode>);
  } else if (taskFixture) {
    root.render(<StrictMode><TasksProduction store={fixtureTaskStore(taskFixture)} fixture={taskFixture} locale={locale} translate={translateTasks} now={TASK_FIXED_NOW} onReady={() => emitReady(`fixture:${taskFixture}`)} /></StrictMode>);
  } else if (conversationFixture) {
    root.render(<StrictMode><ConversationsProduction store={fixtureConversationStore(conversationFixture, requestedQa === "conversation-detail")} foldersStore={fixtureFolderStore()} fixture={conversationFixture} detailId={detailId} locale={locale} onReady={() => emitReady(`fixture:${conversationFixture}`)} /></StrictMode>);
  } else if (memoryFixture) {
    root.render(<StrictMode><MemoriesProduction store={fixtureStore(memoryFixture)} fixture={memoryFixture} locale={locale} onReady={() => emitReady(`fixture:${memoryFixture}`)} /></StrictMode>);
  } else if (route === "unsupported") {
    root.render(<StrictMode>{unsupportedRoute()}</StrictMode>);
    emitReady("unsupported");
  } else if (!isBridgeHttpAvailable()) {
    root.render(<StrictMode>{bridgeUnavailable()}</StrictMode>);
    emitReady("bridge-unavailable");
  } else {
    const profile = query.get("profile")?.trim() || "default";
    void (async () => {
      try {
        const bridge = await openWebStorageBridge(profile);
        const http = bridgeHttpClient();
        // COORD-degradation-is-unobservable: dev/QA builds get the on-disk
        // adapter, not the in-memory one — a degradation from an overnight
        // run must still be there in the morning.
        const env = realEnv(await openOnDiskFallbackSink(bridge));
        // One factory for every route. `PlatformProductionStoreFactory` extends the legacy
        // one, so legacy domains behave identically whatever the selection says — which is
        // what lets Memories move generation without Tasks/Conversations/Folders moving.
        //
        // Both transports resolve through the same bridge channel today because
        // `BridgeHttpRequest` carries no binding selector: the shell holds exactly one base
        // URL. That means single-origin operation — point the shell at the platform service
        // and the platform read path is live. Two ORIGINS at once needs an additive
        // `binding` field on the bridge request, which is FE-CORE's contract to change; see
        // blocked/FE-SURFACES-bridge-two-origin-binding.md. Passing the same client twice is
        // stated here rather than hidden, because the silent version of this is exactly how
        // a client ends up reading the legacy wire while believing it is on the new one.
        const platform = createPlatformProductionStoreFactory(
          bridge,
          env,
          {
            legacyHttp: http,
            platformHttp: http,
            ...(route === "chat"
              ? {
                  platformStream: bridgeStreamPort(),
                  chatAttachmentStaging: bridgeChatAttachmentStagingPort(),
                }
              : {}),
          },
          generationSelection,
        );
        const stores = platform;
        if (route === "memories" && platform.selection.memories === "platform") {
          const store = await platform.openSynthesizedMemories();
          await store.refresh();
          markRendered("memories-platform", "platform");
          root.render(<StrictMode><MemoriesPlatformProduction store={store} source={{ kind: "live", origin: hostConfig.platformOriginLabel ?? "bridge" }} locale={locale} onReady={() => emitReady("bridge:platform")} /></StrictMode>);
          return;
        }
        if (route === "home") {
          const [memories, conversations] = await Promise.all([
            stores.openMemories(),
            stores.openConversations(),
          ]);
          await Promise.allSettled([memories.refresh(), conversations.refresh()]);
          markRendered("home", "legacy");
          root.render(<StrictMode><HomeProduction sources={{ memories, conversations }} source={{ kind: "live", origin: hostConfig.platformOriginLabel ?? "bridge" }} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else if (route === "tasks") {
          const store = await stores.openTasks();
          markRendered("tasks", null);
          root.render(<StrictMode><TasksProduction store={store} locale={locale} translate={translateTasks} now={env.now()} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else if (route === "conversations") {
          const [store, foldersStore] = await Promise.all([
            stores.openConversations(),
            stores.openFolders(),
          ]);
          markRendered("conversations", null);
          root.render(<StrictMode><ConversationsProduction store={store} foldersStore={foldersStore} detailId={detailId} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else if (route === "folders") {
          const store = await stores.openFolders();
          markRendered("folders", null);
          root.render(<StrictMode><FoldersProduction store={store} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else if (route === "listen") {
          const openSocket = hostConfig.listenSocketFactory
            ?? createProductionListenHostSocketFactory();
          const schema = JSON.parse(__OMI_LISTEN_PROTOCOL_SCHEMA__) as SchemaDocument;
          const client = createPlatformListenCaptureClient({
            env,
            schema,
            openSocket,
            generation: "platform",
            handshake: { language: locale, source: listenSource },
          });
          const store = createPlatformProductionListenStore(client, env);
          markRendered("listen", null);
          root.render(<StrictMode><ListenProduction store={store} locale={locale} onReady={() => emitReady("bridge:platform-listen")} /></StrictMode>);
        } else if (route === "chat") {
          const store = await platform.openChat();
          markRendered("chat", null);
          root.render(<StrictMode><ChatProduction store={store} locale={locale} onReady={() => emitReady("bridge:platform-chat")} /></StrictMode>);
        } else if (route === "settings") {
          const store = await createPlatformProductionSettingsStore(http, appearancePreference);
          markRendered("settings", null);
          root.render(<StrictMode><SettingsProduction store={store} locale={locale} onReady={() => emitReady("bridge:platform-settings")} /></StrictMode>);
        } else if (route === "memories") {
          const store = await stores.openMemories();
          markRendered("memories-legacy", "legacy");
          root.render(<StrictMode><MemoriesProduction store={store} locale={locale} onReady={() => emitReady("bridge")} /></StrictMode>);
        } else {
          root.render(<StrictMode>{unsupportedRoute()}</StrictMode>);
          emitReady("unsupported");
        }
      } catch {
        root.render(<StrictMode>{bridgeUnavailable()}</StrictMode>);
        emitReady("bridge-unavailable");
      }
    })();
  }
}
