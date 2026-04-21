import { useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useWhisprStore } from "@/stores/whisprStore";

interface TranscriptPartial {
  text: string;
  is_final: boolean;
}

/**
 * Global PTT orchestration. Runs in the main window so it still works
 * even if the floating bar window hasn't been shown yet (its webview
 * doesn't mount until first reveal on some platforms).
 *
 * On ptt:start — start audio capture.
 * On transcript:partial — accumulate.
 * On ptt:stop — stop capture, assemble final text, write to clipboard,
 *   attempt auto-paste, push to Whispr history.
 */
export function usePttSession(): void {
  const finalSegmentsRef = useRef<string[]>([]);
  const interimRef = useRef<string>("");
  const startedAtRef = useRef<number | null>(null);
  const activeRef = useRef(false);

  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    listen("ptt:start", () => {
      console.info("[PTT] ptt:start received");
      finalSegmentsRef.current = [];
      interimRef.current = "";
      startedAtRef.current = Date.now();
      activeRef.current = true;
      // Show the dedicated Whispr HUD (its own window, bottom-center).
      // We don't reuse the chat floating bar — separate surface, separate
      // concerns.
      invoke("show_whispr_hud").catch((err) => {
        console.warn("[PTT] show_whispr_hud failed:", err);
      });
      invoke("plugin:audio-capture|start_recording").catch((err) => {
        console.warn("[PTT] start_recording failed:", err);
      });
    }).then((u) => unlisteners.push(u));

    listen<TranscriptPartial>("transcript:partial", (e) => {
      if (!activeRef.current) return;
      const p = e.payload;
      if (p.is_final) {
        if (p.text.trim()) finalSegmentsRef.current.push(p.text.trim());
        interimRef.current = "";
      } else {
        interimRef.current = p.text;
      }
      // Push the rolling transcript through Rust so `app.emit` broadcasts
      // it to every window, including the Whispr HUD. `emitTo` from JS
      // didn't reliably deliver to the freshly-shown HUD.
      const combined = [
        ...finalSegmentsRef.current,
        interimRef.current,
      ]
        .filter((s) => s && s.trim().length > 0)
        .join(" ");
      void invoke("whispr_push_live", {
        text: combined,
        isFinal: p.is_final,
      });
    }).then((u) => unlisteners.push(u));

    listen("ptt:stop", () => {
      console.info("[PTT] ptt:stop received");
      const startedAt = startedAtRef.current;
      startedAtRef.current = null;
      activeRef.current = false;

      (async () => {
        try {
          await invoke("plugin:audio-capture|stop_recording");
        } catch (err) {
          console.warn("[PTT] stop_recording failed:", err);
        }
        // Audio consumer flushes its final partial after stop — give it
        // a beat so we don't miss the tail of the utterance.
        await new Promise((resolve) => setTimeout(resolve, 400));

        const finals = [...finalSegmentsRef.current, interimRef.current]
          .filter((s) => s && s.trim().length > 0)
          .join(" ")
          .trim();

        finalSegmentsRef.current = [];
        interimRef.current = "";

        // Hide the Whispr HUD before attempting keystroke injection so
        // the simulated Ctrl+V goes to the previously focused app, not
        // the HUD window.
        invoke("hide_whispr_hud").catch(() => {});

        if (!finals) {
          console.info("[PTT] no transcript text — nothing to paste");
          return;
        }

        const durationMs = startedAt ? Date.now() - startedAt : undefined;

        // `paste_transcript` snapshots the current clipboard, writes the
        // transcript, simulates Ctrl+V, then restores the original
        // clipboard. The user's previous clipboard survives.
        let autoPasted = false;
        try {
          await invoke("paste_transcript", { text: finals });
          autoPasted = true;
          console.info("[PTT] pasted + clipboard restored");
        } catch (err) {
          console.warn("[PTT] paste_transcript failed:", err);
          // Fallback: if simulated paste errored, leave the transcript on
          // the clipboard so the user can at least Ctrl+V manually. They
          // lose their previous clipboard in this branch, but that's the
          // same behaviour as before.
          try {
            await invoke("copy_to_clipboard", { text: finals });
          } catch (err2) {
            console.warn("[PTT] copy_to_clipboard fallback failed:", err2);
          }
        }

        // Whispr history always captures the transcript so the user can
        // recopy it later even though the clipboard has been restored.
        useWhisprStore.getState().record({
          text: finals,
          durationMs,
          autoPasted,
        });
      })();
    }).then((u) => unlisteners.push(u));

    return () => {
      unlisteners.forEach((u) => u());
    };
  }, []);
}
