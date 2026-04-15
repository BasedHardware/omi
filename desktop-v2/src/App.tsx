import { Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import { TooltipProvider } from "./components/ui/tooltip";
import { useAuthStore } from "./stores/authStore";
import { Sidebar } from "./components/sidebar/Sidebar";
import { ChatPage } from "./components/chat/ChatPage";
import { ConversationsPage } from "./components/conversations/ConversationsPage";
import { TasksPage } from "./components/tasks/TasksPage";
import { MemoriesPage } from "./components/memories/MemoriesPage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { RewindPage } from "./components/rewind/RewindPage";
import { FocusPage } from "./components/focus/FocusPage";
import { MemoryIndicator } from "./components/settings/MemoryIndicator";

function App() {
  const { isSignedIn, isLoading, isSigningIn, error, signIn, restoreSession } =
    useAuthStore();

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  if (isLoading) {
    return (
      <div className="app-container">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (!isSignedIn) {
    return (
      <div className="app-container">
        <div className="auth-screen">
          <h1>Nooto</h1>
          <p>AI-powered desktop companion</p>
          <div className="auth-buttons">
            <button
              onClick={() => signIn("google")}
              className="sign-in-button google"
              disabled={isSigningIn}
            >
              {isSigningIn ? "Waiting for browser..." : "Sign in with Google"}
            </button>
            <button
              onClick={() => signIn("apple")}
              className="sign-in-button apple"
              disabled={isSigningIn}
            >
              {isSigningIn ? "Waiting for browser..." : "Sign in with Apple"}
            </button>
          </div>
          {isSigningIn && (
            <p className="auth-hint">
              Complete sign-in in your browser, then return here.
            </p>
          )}
          {error && <p className="auth-error">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="app-container">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/meetings" element={<ConversationsPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/memories" element={<MemoriesPage />} />
            <Route path="/rewind" element={<RewindPage />} />
            <Route path="/focus" element={<FocusPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
        <MemoryIndicator />
      </div>
    </TooltipProvider>
  );
}

export default App;
