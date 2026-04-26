import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { TooltipProvider } from "./components/ui/tooltip";
import { useAuthStore } from "./stores/authStore";
import { useOnboardingStore } from "./stores/onboardingStore";
import { LoginScreen } from "./components/auth/LoginScreen";
import { OnboardingShell } from "./components/onboarding/OnboardingShell";
import { Sidebar } from "./components/sidebar/Sidebar";
import { DashboardPage } from "./components/dashboard/DashboardPage";
import { ChatPage } from "./components/chat/ChatPage";
import { GoalsHistoryPage } from "./components/goals/GoalsHistoryPage";
import { GoalCelebrationOverlay } from "./components/goals/GoalCelebrationOverlay";
import { SettingsPage } from "./components/settings/SettingsPage";
import { AppsPage } from "./components/apps/AppsPage";
import { DeviceSettingsPage } from "./components/devices/DeviceSettingsPage";
import { LibraryPage } from "./components/library/LibraryPage";
import { PlanPage } from "./components/plan/PlanPage";
import { MemoryIndicator } from "./components/settings/MemoryIndicator";
import {
  startTaskDeduplication,
  stopTaskDeduplication,
} from "./services/taskDeduplicationService";
import { useTraySync } from "./hooks/useTraySync";
import { usePttSession } from "./hooks/usePttSession";
import { useGoalStore } from "./stores/goalStore";
import { useFocusStore } from "./stores/focusStore";
import { useRewindStore } from "./stores/rewindStore";
import { useChatStore } from "./stores/chatStore";
import {
  initMemoryAssistant,
  stopMemoryAssistant,
} from "./services/memoryAssistant";
import { initCompanion, destroyCompanion } from "./services/companion";
import {
  startTaskTrigger,
  stopTaskTrigger,
} from "./services/proactiveTaskTrigger";
import { useMemoryAssistantSettings } from "./services/memoryAssistantSettings";
import { useTaskAssistantSettings } from "./services/taskAssistantSettings";

type ZustandSubscribe<S> = (
  listener: (state: S, prevState: S) => void,
) => () => void;

function App() {
  const { isSignedIn, isLoading, restoreSession } = useAuthStore();
  // Bind directly to the store so resets re-render immediately. Holding this
  // in local state caused stale reads after `resetOnboarding()`.
  const onboardingDone = useOnboardingStore((s) => s.hasCompletedOnboarding);

  useTraySync();
  usePttSession();
  const navigate = useNavigate();

  // When the user clicks an OS notification, the stub Nooto.app opens
  // `nooto://notification-click` which the Rust deep-link handler turns into a
  // `notification:click` event. Pull the stored title+body, route to chat, and
  // send the body so the assistant can respond in context.
  useEffect(() => {
    let unlisten: UnlistenFn | null = null;
    (async () => {
      unlisten = await listen("notification:click", async () => {
        try {
          const payload = await invoke<[string, string] | null>(
            "take_last_notification",
          );
          if (!payload) return;
          const [, body] = payload;
          if (!body.trim()) return;
          navigate("/chat");
          // Defer to next microtask so <ChatPage> mounts before sendMessage.
          queueMicrotask(() => {
            void useChatStore.getState().sendMessage(body);
          });
        } catch (err) {
          console.error("[notification:click] handler failed", err);
        }
      });
    })();
    return () => {
      unlisten?.();
    };
  }, [navigate]);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  // Sync the persisted PTT key to the Rust listener on every boot. The
  // listener is opt-in (see ptt::start_listener) and defaults to AltGr —
  // without this call, a Ctrl chord the user picked during onboarding
  // wouldn't trigger dictation after relaunch.
  useEffect(() => {
    const chord = useOnboardingStore.getState().voiceShortcut;
    const key = chord?.split("+").pop()?.trim();
    if (!key) return;
    import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke("set_ptt_key", { label: key }))
      .catch((err) => console.warn("[ptt] set_ptt_key on boot failed:", err));
  }, []);

  // Boot the Companion service — pre-creates overlay windows and wires PTT events.
  useEffect(() => {
    initCompanion().catch((err) =>
      console.warn("[companion] init failed:", err),
    );
    return () => {
      destroyCompanion();
    };
  }, []);

  useEffect(() => {
    if (!isSignedIn) return;
    startTaskDeduplication();
    // Warm the goal store so FocusAssistant's context enrichment has data
    // before the first screenshot analysis.
    useGoalStore.getState().loadGoals(true);
    // Auto-resume Rewind monitoring + capture if the flags say they're on.
    // Both `startFocusMonitoring` and `startCapture` are idempotent and the
    // commercial-hours watcher will pause capture outside work windows.
    if (useFocusStore.getState().focusEnabled) {
      useFocusStore.getState().startFocusMonitoring();
    }
    if (useRewindStore.getState().rewindEnabled) {
      void useRewindStore.getState().startCapture();
    }

    // Proactive memory + task extraction — matches Swift ProactiveAssistants.
    // Each pipeline is gated by its settings `enabled` flag and reacts to
    // runtime toggles from the Settings UI.
    const syncAssistant = <S extends { enabled: boolean }>(
      store: { getState: () => S; subscribe: ZustandSubscribe<S> },
      start: () => void,
      stop: () => void,
    ) => {
      if (store.getState().enabled) start();
      const unsub = store.subscribe((s, prev) => {
        if (s.enabled === prev.enabled) return;
        if (s.enabled) start();
        else stop();
      });
      return () => {
        unsub();
        stop();
      };
    };

    const teardownMemory = syncAssistant(
      useMemoryAssistantSettings,
      initMemoryAssistant,
      stopMemoryAssistant,
    );
    const teardownTask = syncAssistant(
      useTaskAssistantSettings,
      startTaskTrigger,
      stopTaskTrigger,
    );

    return () => {
      stopTaskDeduplication();
      teardownMemory();
      teardownTask();
    };
  }, [isSignedIn]);

  if (isLoading) {
    return (
      <div className="app-container">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (!isSignedIn) {
    return <LoginScreen />;
  }

  if (!onboardingDone) {
    // markCompleted() in the shell flips the store; the binding above
    // re-renders us into the dashboard. No callback needed.
    return <OnboardingShell onComplete={() => {}} />;
  }

  return (
    <TooltipProvider>
      <div className="app-container">
        <Sidebar />
        <main className="main-content">
          <KeepAliveRoutes />
        </main>
        <MemoryIndicator />
        <GoalCelebrationOverlay />
      </div>
    </TooltipProvider>
  );
}

// Pre-Library/Plan routes — kept as redirects so old deep links and
// in-app `navigate("/tasks")` calls land on the new tabbed surface.
const LEGACY_REDIRECTS: Record<string, string> = {
  "/meetings": "/library/meetings",
  "/memories": "/library/memories",
  "/rewind": "/library/rewind",
  "/focus": "/library/rewind",
  "/whispr": "/library/whispr",
  "/tasks": "/plan/tasks",
  "/goals": "/plan/goals",
  "/insights": "/plan/insights",
};

function KeepAliveRoutes() {
  const { pathname } = useLocation();
  const match = (path: string) =>
    path === "/" ? pathname === "/" : pathname.startsWith(path);
  const dashboardActive = pathname === "/" || match("/dashboard");

  // Match legacy paths exactly (or with a trailing slash) — sub-paths like
  // /library/meetings must NOT match /meetings.
  const legacyTarget =
    LEGACY_REDIRECTS[pathname] ??
    (pathname.endsWith("/")
      ? LEGACY_REDIRECTS[pathname.slice(0, -1)]
      : undefined);
  if (legacyTarget) {
    return <Navigate to={legacyTarget} replace />;
  }

  return (
    <>
      <KeepAlivePane active={dashboardActive}><DashboardPage /></KeepAlivePane>
      <KeepAlivePane active={match("/chat")}><ChatPage /></KeepAlivePane>
      <KeepAlivePane active={match("/library")}><LibraryPage /></KeepAlivePane>
      <KeepAlivePane active={match("/plan")}><PlanPage /></KeepAlivePane>
      <KeepAlivePane active={match("/goals/history")}><GoalsHistoryPage /></KeepAlivePane>
      <KeepAlivePane active={match("/apps")}><AppsPage /></KeepAlivePane>
      <KeepAlivePane active={match("/devices")}><DeviceSettingsPage /></KeepAlivePane>
      <KeepAlivePane active={match("/settings")}><SettingsPage /></KeepAlivePane>
    </>
  );
}

/**
 * Lazy keep-alive: the child is not rendered until `active` becomes true for
 * the first time. After that it stays mounted; visibility toggles via
 * `display: none`. This gives instant route transitions on revisits while
 * avoiding the cold-start cost of mounting every screen on app launch.
 */
function KeepAlivePane({ active, children }: { active: boolean; children: React.ReactNode }) {
  const everActive = useRef(false);
  if (active) everActive.current = true;
  if (!everActive.current) return null;
  return (
    <div
      style={{
        display: active ? "flex" : "none",
        flex: 1,
        minHeight: 0,
        flexDirection: "column",
      }}
    >
      {children}
    </div>
  );
}

export default App;
