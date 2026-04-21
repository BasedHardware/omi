import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Button } from "@/components/ui/button";

interface PttDiagnostics {
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

interface TranscriptPartial {
  text: string;
  is_final: boolean;
}

interface LogLine {
  ts: number;
  source: string;
  detail: string;
}

const MAX_LOG = 40;

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour12: false });
}

function StatusDot({
  ok,
  warn,
}: {
  ok?: boolean;
  warn?: boolean;
}) {
  const color = ok
    ? "bg-emerald-500"
    : warn
      ? "bg-amber-500"
      : "bg-destructive";
  return <span className={`inline-block size-2 rounded-full ${color}`} />;
}

/**
 * Developer-mode diagnostics for the AltGr push-to-talk flow.
 *
 * Surfaces: did the rdev listener start? How many raw key events has it
 * seen? How many ptt:start / ptt:stop events fired? What was the last
 * key? What transcripts have arrived? Plus a "Simulate" button that
 * fires a synthetic ptt:start / ptt:stop pair through the exact same
 * code path the keyboard hook would use.
 */
export function PttDebugPanel() {
  const [diag, setDiag] = useState<PttDiagnostics | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [simulating, setSimulating] = useState(false);
  const logRef = useRef(log);
  logRef.current = log;

  const pushLog = (source: string, detail: string) => {
    const entry: LogLine = { ts: Date.now(), source, detail };
    const next = [entry, ...logRef.current].slice(0, MAX_LOG);
    logRef.current = next;
    setLog(next);
  };

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await invoke<PttDiagnostics>("ptt_diagnostics");
        if (!cancelled) setDiag(next);
      } catch (err) {
        if (!cancelled) {
          pushLog("invoke", `ptt_diagnostics failed: ${String(err)}`);
        }
      }
    };
    poll();
    const id = setInterval(poll, 500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const unlisteners: Array<() => void> = [];
    listen("ptt:start", () => pushLog("event", "ptt:start")).then((u) =>
      unlisteners.push(u),
    );
    listen("ptt:stop", () => pushLog("event", "ptt:stop")).then((u) =>
      unlisteners.push(u),
    );
    listen<TranscriptPartial>("transcript:partial", (e) =>
      pushLog(
        "transcript",
        `${e.payload.is_final ? "FINAL" : "partial"} · ${e.payload.text.slice(0, 80)}`,
      ),
    ).then((u) => unlisteners.push(u));
    return () => unlisteners.forEach((u) => u());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSimulate = async () => {
    setSimulating(true);
    pushLog("action", "Simulate PTT pressed");
    try {
      await invoke("ptt_fire_test");
      pushLog("action", "Simulate PTT completed");
    } catch (err) {
      pushLog("action", `Simulate PTT failed: ${String(err)}`);
    } finally {
      setSimulating(false);
    }
  };

  const handleStartAudio = async () => {
    pushLog("action", "Start audio recording");
    try {
      await invoke("plugin:audio-capture|start_recording");
      pushLog("action", "start_recording OK");
    } catch (err) {
      pushLog("action", `start_recording failed: ${String(err)}`);
    }
  };

  const handleStopAudio = async () => {
    pushLog("action", "Stop audio recording");
    try {
      await invoke("plugin:audio-capture|stop_recording");
      pushLog("action", "stop_recording OK");
    } catch (err) {
      pushLog("action", `stop_recording failed: ${String(err)}`);
    }
  };

  const handleClipboardTest = async () => {
    pushLog("action", "Writing 'Nooto test' to clipboard");
    try {
      await invoke("copy_to_clipboard", { text: "Nooto test" });
      pushLog("action", "clipboard write OK");
    } catch (err) {
      pushLog("action", `clipboard write failed: ${String(err)}`);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border/50 bg-card/40 p-4">
      <div className="flex items-baseline justify-between">
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-medium text-foreground">
            PTT diagnostics
          </span>
          <span className="text-[11px] text-muted-foreground/70">
            Trace the AltGr → audio → clipboard pipeline.
          </span>
        </div>
      </div>

      {/* Status grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px] md:grid-cols-3">
        <Row
          label="Listener thread"
          value={diag?.listener_thread_started ? "started" : "not started"}
          ok={diag?.listener_thread_started}
          warn={diag != null && !diag.listener_thread_started}
        />
        <Row
          label="rdev::listen"
          value={
            diag == null
              ? "—"
              : diag.listener_failed
                ? "failed"
                : diag.listener_thread_started
                  ? "running"
                  : "not started"
          }
          ok={diag?.listener_thread_started && !diag?.listener_failed}
          warn={diag?.listener_failed}
        />
        <Row
          label="Key events seen"
          value={String(diag?.total_key_events ?? 0)}
          warn={diag != null && diag.total_key_events === 0}
        />
        <Row
          label="Last key"
          value={diag?.last_key ?? "—"}
          mono
        />
        <Row label="PTT held?" value={diag?.ptt_down ? "yes" : "no"} />
        <Row
          label="Session active?"
          value={diag?.is_active ? "yes" : "no"}
        />
        <Row
          label="ptt:start fired"
          value={String(diag?.ptt_start_count ?? 0)}
        />
        <Row
          label="ptt:stop fired"
          value={String(diag?.ptt_stop_count ?? 0)}
        />
      </div>

      {diag?.listener_error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
          <span className="font-medium">Listener error:</span>{" "}
          <span className="font-mono">{diag.listener_error}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={handleSimulate}
          disabled={simulating}
        >
          {simulating ? "Simulating…" : "Simulate PTT"}
        </Button>
        <Button size="sm" variant="secondary" onClick={handleStartAudio}>
          Start audio
        </Button>
        <Button size="sm" variant="secondary" onClick={handleStopAudio}>
          Stop audio
        </Button>
        <Button size="sm" variant="secondary" onClick={handleClipboardTest}>
          Test clipboard
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setLog([])}
          className="ml-auto"
        >
          Clear log
        </Button>
      </div>

      {/* Log */}
      <div className="max-h-48 overflow-y-auto rounded-md border border-border/50 bg-background/40 p-2 text-[11px] font-mono leading-tight">
        {log.length === 0 ? (
          <div className="text-muted-foreground/60">No events yet…</div>
        ) : (
          log.map((line, i) => (
            <div key={i} className="flex gap-2">
              <span className="shrink-0 text-muted-foreground/60">
                {formatTime(line.ts)}
              </span>
              <span
                className={`shrink-0 w-20 uppercase tracking-wide ${sourceColor(line.source)}`}
              >
                {line.source}
              </span>
              <span className="min-w-0 break-all text-foreground/85">
                {line.detail}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function sourceColor(source: string): string {
  if (source === "event") return "text-primary";
  if (source === "transcript") return "text-emerald-400";
  if (source === "action") return "text-amber-400";
  return "text-muted-foreground";
}

function Row({
  label,
  value,
  ok,
  warn,
  mono,
}: {
  label: string;
  value: string;
  ok?: boolean;
  warn?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      {(ok !== undefined || warn !== undefined) && (
        <StatusDot ok={ok} warn={warn} />
      )}
      <span className="text-muted-foreground">{label}</span>
      <span
        className={`ml-auto text-foreground ${mono ? "font-mono text-[11px]" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
