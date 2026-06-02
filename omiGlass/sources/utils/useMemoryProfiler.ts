import * as React from 'react';

interface MemorySnapshot {
  timestamp: number;
  jsHeapUsed: number;    // MB
  jsHeapTotal: number;   // MB
  rss: number;           // MB (if available)
  growthSinceLast: number; // MB delta
}

interface MemoryProfilerOptions {
  /** Interval between snapshots in ms (default: 2000) */
  intervalMs?: number;
  /** Number of snapshots to keep in history (default: 150 = 5 min at 2s) */
  maxSnapshots?: number;
  /** Heap growth threshold in MB to trigger a leak warning (default: 5) */
  leakThresholdMb?: number;
  /** Callback when leak is suspected */
  onLeakDetected?: (snapshot: MemorySnapshot, history: MemorySnapshot[]) => void;
}

interface MemoryProfilerResult {
  /** Latest memory snapshot */
  current: MemorySnapshot | null;
  /** All recorded snapshots */
  history: MemorySnapshot[];
  /** Whether a potential leak was detected */
  leakDetected: boolean;
  /** Total growth since profiling started (MB) */
  totalGrowthMb: number;
  /** Average growth rate (MB/min) */
  growthRateMbPerMin: number;
  /** Take an immediate snapshot */
  takeSnapshot: () => MemorySnapshot | null;
}

function getMemoryUsage(): { jsHeapUsed: number; jsHeapTotal: number; rss: number } | null {
  // 1. Hermes internal stats (React Native Android/iOS)
  const hermesInternal = (global as any).HermesInternal;
  if (hermesInternal?.getInstrumentedStats) {
    try {
      const stats = hermesInternal.getInstrumentedStats();
      const used = stats['hermes.jsHeapSize'] ?? stats['js Heap Size'] ?? 0;
      const total = stats['hermes.heapCapacity'] ?? stats['js Heap Capacity'] ?? used * 2;
      if (used > 0) {
        return {
          jsHeapUsed: used / (1024 * 1024),
          jsHeapTotal: total / (1024 * 1024),
          rss: 0,
        };
      }
    } catch (e) {
      // getInstrumentedStats not available in this Hermes build
    }
  }

  // 2. Web/V8 (Chrome DevTools, Expo web)
  const performance = global.performance as any;
  if (performance?.memory) {
    return {
      jsHeapUsed: performance.memory.usedJSHeapSize / (1024 * 1024),
      jsHeapTotal: performance.memory.totalJSHeapSize / (1024 * 1024),
      rss: performance.memory.rss ? performance.memory.rss / (1024 * 1024) : 0,
    };
  }

  return null;
}

export function useMemoryProfiler(options: MemoryProfilerOptions = {}): MemoryProfilerResult {
  const {
    intervalMs = 2000,
    maxSnapshots = 150,
    leakThresholdMb = 5,
    onLeakDetected,
  } = options;

  const [current, setCurrent] = React.useState<MemorySnapshot | null>(null);
  const [leakDetected, setLeakDetected] = React.useState(false);
  const historyRef = React.useRef<MemorySnapshot[]>([]);
  const baselineRef = React.useRef<MemorySnapshot | null>(null);

  // Use refs for callbacks to avoid recreating takeSnapshot / resetting the interval
  const onLeakDetectedRef = React.useRef(onLeakDetected);
  onLeakDetectedRef.current = onLeakDetected;

  const takeSnapshot = React.useCallback((): MemorySnapshot | null => {
    const mem = getMemoryUsage();
    if (!mem) return null;

    const prev = historyRef.current.length > 0
      ? historyRef.current[historyRef.current.length - 1]
      : null;

    const snapshot: MemorySnapshot = {
      timestamp: Date.now(),
      jsHeapUsed: mem.jsHeapUsed,
      jsHeapTotal: mem.jsHeapTotal,
      rss: mem.rss,
      growthSinceLast: prev ? mem.jsHeapUsed - prev.jsHeapUsed : 0,
    };

    // Record baseline
    if (!baselineRef.current) {
      baselineRef.current = snapshot;
    }

    // Append to history (capped)
    historyRef.current.push(snapshot);
    if (historyRef.current.length > maxSnapshots) {
      historyRef.current = historyRef.current.slice(-maxSnapshots);
    }

    // Check for sustained growth: >30% of last 20 snapshots show growth > 1 MB
    // and total growth exceeds the leak threshold
    const WINDOW = 20;
    const recent = historyRef.current.slice(-WINDOW);
    const growingSnapshots = recent.filter(s => s.growthSinceLast > 1).length;

    if (growingSnapshots > recent.length * 0.3) {
      const totalGrowth = snapshot.jsHeapUsed - (baselineRef.current?.jsHeapUsed ?? snapshot.jsHeapUsed);
      if (totalGrowth > leakThresholdMb) {
        setLeakDetected(true);
        onLeakDetectedRef.current?.(snapshot, historyRef.current);
      }
    }

    setCurrent(snapshot);
    return snapshot;
  }, [maxSnapshots, leakThresholdMb]);

  // Periodic sampling
  React.useEffect(() => {
    // Take first snapshot immediately
    takeSnapshot();

    const timer = setInterval(takeSnapshot, intervalMs);
    return () => clearInterval(timer);
  }, [takeSnapshot, intervalMs]);

  // Compute derived metrics
  const history = historyRef.current;
  const totalGrowthMb = React.useMemo(() => {
    if (history.length < 2) return 0;
    return history[history.length - 1].jsHeapUsed - history[0].jsHeapUsed;
  }, [history, current]);

  const growthRateMbPerMin = React.useMemo(() => {
    if (history.length < 2) return 0;
    const elapsed = (history[history.length - 1].timestamp - history[0].timestamp) / 60000;
    if (elapsed <= 0) return 0;
    return totalGrowthMb / elapsed;
  }, [history, totalGrowthMb, current]);

  return {
    current,
    history,
    leakDetected,
    totalGrowthMb,
    growthRateMbPerMin,
    takeSnapshot,
  };
}

/**
 * Standalone memory snapshot function for use outside React components.
 * Call from console: global.__takeMemSnapshot()
 */
export function setupGlobalMemorySnapshot(): void {
  (global as any).__takeMemSnapshot = () => {
    const mem = getMemoryUsage();
    if (!mem) {
      console.warn('[MemoryProfiler] No memory API available. Ensure performance.memory is enabled.');
      return null;
    }
    const snapshot = {
      timestamp: new Date().toISOString(),
      jsHeapUsed: `${mem.jsHeapUsed.toFixed(2)} MB`,
      jsHeapTotal: `${mem.jsHeapTotal.toFixed(2)} MB`,
      rss: mem.rss > 0 ? `${mem.rss.toFixed(2)} MB` : 'N/A',
    };
    console.log('[MemoryProfiler] Snapshot:', snapshot);
    return snapshot;
  };
}
