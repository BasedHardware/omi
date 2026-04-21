import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { FloatingBar } from "./components/floating/FloatingBar";
import { NotificationBar } from "./components/notifications/NotificationBar";
import { WhisprLiveHUD } from "./components/whispr/WhisprLiveHUD";
import { LiveTranscriptWindow } from "./components/live-transcript/LiveTranscriptWindow";
import "./styles/globals.css";

// The Tauri auxiliary windows are launched with `?window=<name>` in their URL.
// We pick the root component based on that query param so the same Vite
// bundle serves the main app, the floating composer, the notification bar,
// the Whispr live-transcription HUD, and the live-transcript meeting overlay.
const windowParam = new URLSearchParams(window.location.search).get("window");
const isFloating = windowParam === "floating";
const isNotifications = windowParam === "notifications";
const isWhispr = windowParam === "whispr";
const isLiveTranscript = windowParam === "live-transcript";

if (isFloating || isNotifications || isWhispr || isLiveTranscript) {
  document.documentElement.classList.add("floating-window");
  document.body.classList.add("floating-window");
}
if (isWhispr) {
  document.documentElement.classList.add("whispr-window");
  document.body.classList.add("whispr-window");
}

function Root() {
  if (isFloating) return <FloatingBar />;
  if (isNotifications) return <NotificationBar />;
  if (isWhispr) return <WhisprLiveHUD />;
  if (isLiveTranscript) return <LiveTranscriptWindow />;
  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
