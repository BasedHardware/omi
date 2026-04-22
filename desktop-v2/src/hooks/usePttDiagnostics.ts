import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

export interface PttDiagnostics {
  listener_thread_started: boolean;
  listener_failed: boolean;
  listener_error: string | null;
  ptt_down: boolean;
  is_active: boolean;
  total_key_events: number;
  ptt_start_count: number;
  ptt_stop_count: number;
  last_key: string | null;
}

/** Polls `ptt_diagnostics` on an interval and returns the latest snapshot.
 *  Used by the Developer debug panel and the Shortcuts-pane status row so
 *  both observe the same source of truth. */
export function usePttDiagnostics(intervalMs = 1000): PttDiagnostics | null {
  const [diag, setDiag] = useState<PttDiagnostics | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await invoke<PttDiagnostics>("ptt_diagnostics");
        if (!cancelled) setDiag(next);
      } catch {
        // Swallow — transient failures are expected during boot.
      }
    };
    void poll();
    const id = setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return diag;
}
