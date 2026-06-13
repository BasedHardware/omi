import * as React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useMemoryProfiler, MemorySnapshot } from './useMemoryProfiler';

interface MemoryProfilerOverlayProps {
  /** Whether to show the overlay (default: true in DEV) */
  visible?: boolean;
  /** Position of the overlay */
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
}

/**
 * Floating overlay that shows live JS heap usage, growth rate, and leak warnings.
 */
export function MemoryProfilerOverlay({
  visible = __DEV__,
  position = 'top-right',
}: MemoryProfilerOverlayProps) {
  const [expanded, setExpanded] = React.useState(false);

  // Use a stable ref for the leak callback to avoid resetting the profiler's interval
  const { current, leakDetected, totalGrowthMb, growthRateMbPerMin, history } = useMemoryProfiler({
    intervalMs: 2000,
    leakThresholdMb: 5,
    onLeakDetected: React.useCallback((snap: MemorySnapshot, hist: MemorySnapshot[]) => {
      const startHeap = hist[0]?.jsHeapUsed ?? snap.jsHeapUsed;
      console.warn(
        `[MemoryProfiler] ⚠️ LEAK DETECTED — Heap grew ${(snap.jsHeapUsed - startHeap).toFixed(1)} MB since start`
      );
    }, []),
  });

  if (!visible || !current) return null;

  const positionStyle = positionMap[position];
  const heapColor = leakDetected ? '#FF3B30' : current.jsHeapUsed > 100 ? '#FF9500' : '#34C759';

  return (
    <View style={[styles.container, positionStyle]}>
      <TouchableOpacity
        activeOpacity={0.8}
        onPress={() => setExpanded(!expanded)}
        style={[styles.badge, { borderColor: heapColor }]}
      >
        {/* Compact view */}
        <Text style={styles.heapText}>
          {current.jsHeapUsed.toFixed(1)} MB
        </Text>
        {leakDetected && <Text style={styles.leakIcon}>⚠️</Text>}

        {/* Expanded view */}
        {expanded && (
          <View style={styles.details}>
            <Text style={styles.detailLine}>
              Heap: {current.jsHeapUsed.toFixed(1)} / {current.jsHeapTotal.toFixed(1)} MB
            </Text>
            {current.rss > 0 && (
              <Text style={styles.detailLine}>RSS: {current.rss.toFixed(1)} MB</Text>
            )}
            <Text style={styles.detailLine}>
              Growth: {totalGrowthMb >= 0 ? '+' : ''}{totalGrowthMb.toFixed(2)} MB
            </Text>
            <Text style={styles.detailLine}>
              Rate: {growthRateMbPerMin.toFixed(2)} MB/min
            </Text>
            <Text style={styles.detailLine}>
              Snapshots: {history.length}
            </Text>
            {leakDetected && (
              <Text style={styles.leakWarning}>
                ⚠️ Sustained growth detected — possible leak
              </Text>
            )}
            <Text style={styles.detailHint}>
              Tap chart in React DevTools for heap snapshots
            </Text>
          </View>
        )}
      </TouchableOpacity>
    </View>
  );
}

const positionMap = StyleSheet.create({
  'top-left': { top: 50, left: 10 },
  'top-right': { top: 50, right: 10 },
  'bottom-left': { bottom: 20, left: 10 },
  'bottom-right': { bottom: 20, right: 10 },
});

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    zIndex: 9999,
    elevation: 9999,
  },
  badge: {
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    borderRadius: 8,
    borderWidth: 2,
    paddingHorizontal: 10,
    paddingVertical: 6,
    minWidth: 80,
    alignItems: 'center',
  },
  heapText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  leakIcon: {
    fontSize: 12,
    marginTop: 2,
  },
  details: {
    marginTop: 8,
    alignSelf: 'stretch',
  },
  detailLine: {
    color: '#CCCCCC',
    fontSize: 12,
    marginBottom: 2,
    fontVariant: ['tabular-nums'],
  },
  leakWarning: {
    color: '#FF3B30',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 4,
  },
  detailHint: {
    color: '#888888',
    fontSize: 10,
    marginTop: 6,
    fontStyle: 'italic',
  },
});
