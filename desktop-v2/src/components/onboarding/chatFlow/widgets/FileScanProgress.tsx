import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { LoadingRing } from "../../animations/LoadingRing";
import { Badge } from "@/components/ui/badge";
import type { WidgetResult } from "../types";

interface Props {
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

interface Snapshot {
  file_count: number;
  project_names: string[];
  applications?: string[];
  technologies?: string[];
  complete: boolean;
  current_root: string | null;
}

/** Module-level singleton. The file scan runs at most once per process
 *  lifetime even across StrictMode remounts and back-button re-entries. */
interface ScanSession {
  snapshot: Snapshot;
  subscribers: Set<(snap: Snapshot) => void>;
  started: boolean;
  completed: boolean;
}
let activeSession: ScanSession | null = null;

function ensureSession(): ScanSession {
  if (activeSession) return activeSession;
  const session: ScanSession = {
    snapshot: {
      file_count: 0,
      project_names: [],
      applications: [],
      technologies: [],
      complete: false,
      current_root: null,
    },
    subscribers: new Set(),
    started: false,
    completed: false,
  };
  activeSession = session;

  void (async () => {
    const unlisteners: UnlistenFn[] = [];
    try {
      unlisteners.push(
        await listen<Snapshot>("file_scan:progress", (e) => {
          session.snapshot = e.payload;
          session.subscribers.forEach((fn) => fn(e.payload));
        }),
      );
      unlisteners.push(
        await listen<Snapshot>("file_scan:complete", (e) => {
          session.snapshot = { ...e.payload, complete: true };
          session.completed = true;
          session.subscribers.forEach((fn) => fn(session.snapshot));
        }),
      );
    } catch (err) {
      console.warn("[file_scan] listen failed:", err);
    }

    if (!session.started) {
      session.started = true;
      try {
        await invoke("start_file_scan");
      } catch (err) {
        console.warn("[file_scan] start failed:", err);
        session.completed = true;
        session.snapshot = { ...session.snapshot, complete: true };
        session.subscribers.forEach((fn) => fn(session.snapshot));
      }
    }

    // Listeners are module-scoped; we never detach them — the session is
    // one-shot and lives for the lifetime of the webview.
    void unlisteners;
  })();

  return session;
}

export function FileScanProgressWidget({ disabled, onCapture }: Props) {
  const session = ensureSession();
  const [snapshot, setSnapshot] = useState<Snapshot>(session.snapshot);
  const capturedRef = useRef(false);

  useEffect(() => {
    const onUpdate = (s: Snapshot) => setSnapshot(s);
    session.subscribers.add(onUpdate);
    return () => {
      session.subscribers.delete(onUpdate);
    };
  }, [session]);

  useEffect(() => {
    if (disabled || capturedRef.current) return;
    if (snapshot.complete) {
      capturedRef.current = true;
      const t = window.setTimeout(() => {
        const summary =
          snapshot.project_names.length > 0
            ? `${snapshot.file_count.toLocaleString()} files, ${snapshot.project_names.length} projects`
            : `${snapshot.file_count.toLocaleString()} files scanned`;
        onCapture({ scanDone: true }, summary);
      }, 400);
      return () => window.clearTimeout(t);
    }
  }, [snapshot, disabled, onCapture]);

  // Backstop: never wedge. If no complete event in 20s, force capture.
  useEffect(() => {
    if (disabled || capturedRef.current) return;
    const t = window.setTimeout(() => {
      if (capturedRef.current) return;
      capturedRef.current = true;
      onCapture({ scanDone: true }, "Scan timed out — moved on");
    }, 20_000);
    return () => window.clearTimeout(t);
  }, [disabled, onCapture]);

  return (
    <div className="flex flex-col gap-3 mt-2">
      <div className="flex items-center gap-4">
        <LoadingRing
          size={60}
          progress={snapshot.complete ? 1 : undefined}
          label=""
        />
        <div className="flex flex-col gap-1 min-w-0">
          <div className="text-[14px] font-medium text-foreground">
            {snapshot.complete
              ? "Done."
              : snapshot.current_root
                ? `Scanning ~/${snapshot.current_root}`
                : "Starting…"}
          </div>
          <div className="text-[12px] text-muted-foreground tabular-nums">
            {snapshot.file_count.toLocaleString()} files
            {snapshot.project_names.length > 0
              ? ` · ${snapshot.project_names.length} projects`
              : ""}
          </div>
        </div>
      </div>
      {snapshot.project_names.length > 0 ? (
        <div className="flex items-center gap-1.5 flex-wrap">
          {snapshot.project_names.slice(0, 8).map((p) => (
            <Badge
              key={p}
              variant="secondary"
              className="bg-muted/50 text-muted-foreground border-border/50 text-[11px]"
            >
              {p}
            </Badge>
          ))}
          {snapshot.project_names.length > 8 ? (
            <span className="text-[11px] text-muted-foreground">
              +{snapshot.project_names.length - 8} more
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
