import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { FloatingBar } from "./components/floating/FloatingBar";
import { WhisprLiveHUD } from "./components/whispr/WhisprLiveHUD";
import { LiveTranscriptWindow } from "./components/live-transcript/LiveTranscriptWindow";
import { initTheme } from "./stores/themeStore";
import "./styles/globals.css";

// The Tauri auxiliary windows are launched with `?window=<name>` in their URL.
// We pick the root component based on that query param so the same Vite
// bundle serves the main app, the floating composer, the Whispr HUD, and the
// live-transcript meeting overlay. (Notifications are now OS-native, handled
// entirely in Rust — see `src-tauri/src/commands/notifications.rs`.)
// Keep these window-name strings in sync with the HUD list in the pre-bundle
// FOUC script in `index.html` and the `windows[]` labels in `tauri.conf.json`.
const windowParam = new URLSearchParams(window.location.search).get("window");
const isFloating = windowParam === "floating";
const isWhispr = windowParam === "whispr";
const isLiveTranscript = windowParam === "live-transcript";
const isHudWindow = isFloating || isWhispr || isLiveTranscript;

if (isHudWindow) {
  // HUD overlays are designed against a dark backdrop — force the dark
  // palette regardless of the user's app theme preference.
  document.documentElement.classList.add("dark", "floating-window");
  document.body.classList.add("floating-window");
} else {
  // Apply the user's theme preference before React mounts so we don't flash
  // the default palette on boot.
  initTheme();
}
if (isWhispr) {
  document.documentElement.classList.add("whispr-window");
  document.body.classList.add("whispr-window");
}

function Root() {
  if (isFloating) return <FloatingBar />;
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
