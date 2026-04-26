import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Suggestion } from "@/components/ai-elements/suggestion";
import { Badge } from "@/components/ui/badge";
import type { StepWidget, WidgetResult } from "../types";

interface Props {
  widget: Extract<StepWidget, { type: "permission_grant" }>;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

type Status = "granted" | "waiting" | "not_granted";

/** Permission request bubble. Polls `get_permission_status` every 1s, fires
 *  `request_permission` on grant click, and auto-reports the first flip to
 *  `granted` (with a 450ms pause so the user sees the status update). */
export function PermissionGrantWidget({ widget, disabled, onCapture }: Props) {
  const [status, setStatus] = useState<Status>("not_granted");
  const [error, setError] = useState<string | null>(null);
  const capturedRef = useRef(false);

  useEffect(() => {
    if (disabled) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const next = await invoke<string>("get_permission_status", {
          kind: widget.kind,
        });
        if (cancelled) return;
        if (next === "granted" || next === "waiting" || next === "not_granted") {
          setStatus(next);
        }
      } catch {
        // command might not exist on every platform; don't clobber status
      }
    };

    poll();
    const id = window.setInterval(poll, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [widget.kind, disabled]);

  useEffect(() => {
    if (disabled || capturedRef.current) return;
    if (status === "granted") {
      capturedRef.current = true;
      // Accessibility is gated behind a global rdev listener that is skipped
      // at app startup when TCC says not-trusted. Kick it now so the shortcut-
      // capture step right after onboarding actually receives keys without
      // requiring a full app restart.
      if (widget.kind === "accessibility") {
        invoke("ensure_ptt_listener").catch(() => {});
      }
      const t = window.setTimeout(() => {
        onCapture({ granted: true }, "Granted");
      }, 450);
      return () => window.clearTimeout(t);
    }
  }, [status, disabled, onCapture, widget.kind]);

  const handleRequest = async () => {
    if (disabled) return;
    setError(null);
    setStatus("waiting");
    try {
      await invoke("request_permission", { kind: widget.kind });
    } catch (err) {
      const msg = typeof err === "string" ? err : "Request failed";
      setError(msg);
      setStatus("not_granted");
    }
  };

  const handleSkip = () => {
    if (disabled || capturedRef.current) return;
    capturedRef.current = true;
    onCapture({ granted: false, skipped: true }, "Skipped");
  };

  return (
    <div className="flex flex-col gap-2 mt-2">
      <div className="flex items-center gap-2 flex-wrap">
        <Suggestion
          suggestion="grant"
          onClick={handleRequest}
          disabled={disabled || status === "granted"}
          variant="default"
          className="text-primary-foreground hover:text-primary-foreground border-transparent hover:border-transparent"
        >
          {status === "waiting"
            ? "Opening…"
            : status === "granted"
              ? "Granted"
              : widget.label}
        </Suggestion>
        {widget.skippable ? (
          <Suggestion
            suggestion="skip"
            onClick={handleSkip}
            disabled={disabled || status === "granted"}
          >
            Skip for now
          </Suggestion>
        ) : null}
        <StatusBadge status={status} />
      </div>
      {widget.helper ? (
        <div className="text-[12px] text-muted-foreground">{widget.helper}</div>
      ) : null}
      {error ? (
        <div className="text-[12px] text-destructive">{error}</div>
      ) : null}
    </div>
  );
}

function StatusBadge({ status }: { status: Status }) {
  if (status === "granted") {
    return (
      <Badge
        variant="secondary"
        className="bg-emerald-500/15 text-emerald-300 border-emerald-400/20"
      >
        Granted
      </Badge>
    );
  }
  if (status === "waiting") {
    return (
      <Badge
        variant="secondary"
        className="bg-amber-500/15 text-amber-300 border-amber-400/20"
      >
        Waiting…
      </Badge>
    );
  }
  return (
    <Badge
      variant="secondary"
      className="bg-muted text-muted-foreground border-border"
    >
      Not granted
    </Badge>
  );
}
