import { useEffect, useState } from "react";

/**
 * Returns a human-readable elapsed duration string that ticks every second
 * while `startedAt` is non-null. Returns null when stopped.
 *
 * Format: "12s", "1m 23s", "1h 04m"
 */
export function useElapsed(startedAt: number | null): string | null {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startedAt == null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  if (startedAt == null) return null;
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return formatDuration(seconds);
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${h}h ${mm.toString().padStart(2, "0")}m`;
}
