import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useDevStore } from "../../stores/devStore";

interface MemoryUsage {
  process_bytes: number;
  total_bytes: number;
  used_bytes: number;
}

const POLL_MS = 2000;

function formatMB(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

export function MemoryIndicator() {
  const enabled = useDevStore((s) => s.developerMode && s.memoryIndicatorEnabled);
  const [usage, setUsage] = useState<MemoryUsage | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    const sample = async () => {
      try {
        const result = await invoke<MemoryUsage>("get_memory_usage");
        if (!cancelled) setUsage(result);
      } catch (err) {
        console.error("get_memory_usage failed:", err);
      }
    };

    sample();
    const id = setInterval(sample, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [enabled]);

  if (!enabled || !usage) return null;

  const processMB = formatMB(usage.process_bytes);
  const systemPct =
    usage.total_bytes > 0
      ? Math.round((usage.used_bytes / usage.total_bytes) * 100)
      : 0;

  return (
    <div
      className="fixed bottom-2 right-2 z-50 px-2 py-1 rounded-md bg-background/80 border border-border/60 backdrop-blur-sm text-[11px] font-mono text-muted-foreground tabular-nums pointer-events-none select-none"
      title="Process memory / system memory used"
    >
      {processMB} · sys {systemPct}%
    </div>
  );
}
