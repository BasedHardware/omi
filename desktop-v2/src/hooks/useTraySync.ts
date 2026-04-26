import { useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useFocusStore } from "../stores/focusStore";
import { useAudioStore } from "../stores/audioStore";
import { COMPANION_CUTOVER_ENABLED } from "../config/companionFeatureFlag";

/**
 * Keeps the system tray menu in sync with app state and dispatches tray
 * menu clicks to the right Zustand actions. Call once at the app root.
 *
 * Direction of flow:
 * - State → tray: `focusEnabled` / `audioEnabled` changes trigger
 *   `update_tray_menu` so the CheckMenuItems reflect reality whether
 *   the toggle came from the sidebar or the tray.
 * - Tray → state: menu clicks emit `tray:*` events that run the same
 *   store actions the sidebar does — preserving pre-flight checks
 *   (Gemini API key, commercial-hours deferral).
 */
export function useTraySync(): void {
  // Subscribe via selectors so the effects re-run only when these booleans change.
  const focusEnabled = useFocusStore((s) => s.focusEnabled);
  const audioEnabled = useAudioStore((s) => s.audioEnabled);

  // Push the current state to the tray menu. The `update_tray_menu` command
  // may not be registered in every build (tray module is optional) — silently
  // skip rather than spamming the console on every state change.
  useEffect(() => {
    void invoke("update_tray_menu", {
      auraOn: focusEnabled,
      recordingOn: audioEnabled,
    }).catch(() => {
      // Command not wired in this build — safe to ignore.
    });
  }, [focusEnabled, audioEnabled]);

  // Relabel the "Ask Nooto" tray menu item to "Companion" when the cutover is
  // active. Falls back to "Ask Nooto" when the flag is off (rollback path).
  useEffect(() => {
    const label = COMPANION_CUTOVER_ENABLED ? "Companion" : "Ask Nooto";
    void invoke("set_tray_ask_label", { label }).catch(() => {
      // Tray command not registered in this build — safe to ignore.
    });
  }, []);

  // Handle clicks from the tray menu.
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    const wire = async () => {
      const u1 = await listen("tray:toggle-aura", () => {
        useFocusStore.getState().toggleFocus();
      });
      unlisteners.push(u1);

      const u2 = await listen("tray:toggle-recording", () => {
        void useAudioStore.getState().toggleAudio();
      });
      unlisteners.push(u2);

      // When the cutover is active, "Ask Nooto" in the tray shows the
      // Companion buddy. When off, it toggles the legacy floating bar.
      const u3 = await listen("tray:ask-nooto", () => {
        if (COMPANION_CUTOVER_ENABLED) {
          void invoke("companion_show_buddy");
        } else {
          void invoke("toggle_floating_bar");
        }
      });
      unlisteners.push(u3);

      const u4 = await listen("tray:open-main", () => {
        void invoke("show_main_window");
      });
      unlisteners.push(u4);
    };

    void wire();

    return () => {
      for (const u of unlisteners) u();
    };
  }, []);
}
