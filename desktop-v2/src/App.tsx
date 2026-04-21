import { useLocation } from "react-router-dom";
import { useEffect, useRef } from "react";
import { TooltipProvider } from "./components/ui/tooltip";
import { useAuthStore } from "./stores/authStore";
import { useOnboardingStore } from "./stores/onboardingStore";
import { LoginScreen } from "./components/auth/LoginScreen";
import { OnboardingShell } from "./components/onboarding/OnboardingShell";
import { Sidebar } from "./components/sidebar/Sidebar";
import { DashboardPage } from "./components/dashboard/DashboardPage";
import { ChatPage } from "./components/chat/ChatPage";
import { ConversationsPage } from "./components/conversations/ConversationsPage";
import { TasksPage } from "./components/tasks/TasksPage";
import { GoalsPage } from "./components/goals/GoalsPage";
import { GoalsHistoryPage } from "./components/goals/GoalsHistoryPage";
import { GoalCelebrationOverlay } from "./components/goals/GoalCelebrationOverlay";
import { MemoriesPage } from "./components/memories/MemoriesPage";
import { InsightsPage } from "./components/insights/InsightsPage";
import { WhisprPage } from "./components/whispr/WhisprPage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { AuraPage } from "./components/aura/AuraPage";
import { AppsPage } from "./components/apps/AppsPage";
import { DeviceSettingsPage } from "./components/devices/DeviceSettingsPage";
import { MemoryIndicator } from "./components/settings/MemoryIndicator";
import {
  startTaskDeduplication,
  stopTaskDeduplication,
} from "./services/taskDeduplicationService";
import { useTraySync } from "./hooks/useTraySync";
import { usePttSession } from "./hooks/usePttSession";
import { useGoalStore } from "./stores/goalStore";

function App() {
  const { isSignedIn, isLoading, restoreSession } = useAuthStore();
  // Bind directly to the store so resets re-render immediately. Holding this
  // in local state caused stale reads after `resetOnboarding()`.
  const onboardingDone = useOnboardingStore((s) => s.hasCompletedOnboarding);

  useTraySync();
  usePttSession();

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  useEffect(() => {
    if (!isSignedIn) return;
    startTaskDeduplication();
    // Warm the goal store so FocusAssistant's context enrichment has data
    // before the first screenshot analysis.
    useGoalStore.getState().loadGoals(true);
    return () => stopTaskDeduplication();
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

function KeepAliveRoutes() {
  const { pathname } = useLocation();
  const match = (path: string) =>
    path === "/" ? pathname === "/" : pathname.startsWith(path);
  const auraActive = match("/rewind") || match("/focus");
  // `/` and `/dashboard` both render the dashboard so existing deep links
  // to the root keep working after the home redirect.
  const dashboardActive = pathname === "/" || match("/dashboard");

  return (
    <>
      <KeepAlivePane active={dashboardActive}><DashboardPage /></KeepAlivePane>
      <KeepAlivePane active={match("/chat")}><ChatPage /></KeepAlivePane>
      <KeepAlivePane active={match("/meetings")}><ConversationsPage /></KeepAlivePane>
      <KeepAlivePane active={match("/tasks")}><TasksPage /></KeepAlivePane>
      <KeepAlivePane active={pathname === "/goals"}><GoalsPage /></KeepAlivePane>
      <KeepAlivePane active={match("/goals/history")}><GoalsHistoryPage /></KeepAlivePane>
      <KeepAlivePane active={match("/memories")}><MemoriesPage /></KeepAlivePane>
      <KeepAlivePane active={match("/insights")}><InsightsPage /></KeepAlivePane>
      <KeepAlivePane active={match("/whispr")}><WhisprPage /></KeepAlivePane>
      <KeepAlivePane active={match("/apps")}><AppsPage /></KeepAlivePane>
      <KeepAlivePane active={match("/devices")}><DeviceSettingsPage /></KeepAlivePane>
      <KeepAlivePane active={auraActive}><AuraPage /></KeepAlivePane>
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
