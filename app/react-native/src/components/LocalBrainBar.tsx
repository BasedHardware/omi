import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  type ViewStyle,
} from 'react-native';

// Imported lazily-by-module rather than at the top so the app still renders when
// the native module is absent (Expo Go, tests, iOS). Both wrappers already return
// null / false in that state; this only adds the "why" to the UI.
import { isLocalBrainAvailable } from '../../modules/local-brain';
import {
  isCallDetectionAvailable,
  isSupportedPlatform,
  getCallPermissions,
  requestCallPermissions,
  startCallDetection,
  answerCall,
  hangUp,
  type CallState,
} from '../../modules/local-calls';
import { ROUTE_PROTOTYPES, type Route } from '../services/localBrainRouter';
import { useTheme } from '../hooks/use-theme';
import { Spacing } from '../constants/theme';

export type BrainState = 'absent' | 'not-loaded' | 'ready';

/**
 * The token set in constants/theme.ts is neutral-only (text, background,
 * backgroundElement, backgroundSelected, textSecondary) with no semantic
 * colours, so ready / needs-attention / off cannot be derived from it without
 * inventing a green and an amber here anyway. Declared once, in one place, so
 * there is a single thing to move into the theme when it grows semantic tokens.
 */
const STATUS = {
  ready: '#4ade80',
  warn: '#fbbf24',
  off: '#6b7280',
  accept: '#16a34a',
  decline: '#b91c1c',
  onAccent: '#ffffff',
} as const;

export interface RouteTrace {
  source: 'router' | 'heuristic'
  route: Route
  margin: number
  reason?: string
}

/**
 * Local-brain status and routing transparency.
 *
 * The margin is shown on purpose. A routing layer the user cannot inspect is a
 * black box that will eventually act on the wrong thing, and the margin is the
 * number that says how close that was. Measured on a budget Android phone, this
 * router takes ~600 ms per call at 285 MB, which is fast enough to be invisible
 * and that is exactly why the trace should not be.
 */
export function LocalBrainBar({
  trace,
  onCallState,
}: {
  trace?: RouteTrace | null
  onCallState?: (state: CallState) => void
}) {
  const theme = useTheme();
  const styles = makeStyles(theme);

  const [state] = useState<BrainState>(() =>
    isLocalBrainAvailable ? 'not-loaded' : 'absent'
  );
  const [canAnswer, setCanAnswer] = useState(false);
  const [ringing, setRinging] = useState(false);
  const [showDetail, setShowDetail] = useState(false);

  // Permission state is informational: detection and answering are separate
  // grants, and the UI should say which one is missing rather than implying
  // neither works.
  useEffect(() => {
    if (!isCallDetectionAvailable || !isSupportedPlatform) return
    getCallPermissions()
      .then((p) => setCanAnswer(p.canAnswer))
      .catch(() => setCanAnswer(false))
  }, [])

  useEffect(() => {
    if (!isCallDetectionAvailable || !isSupportedPlatform) return
    let cancelled = false
    // Ask, then listen. Both prompts are runtime grants and either can be
    // revoked, so this re-checks rather than assuming.
    requestCallPermissions()
      .then((p) => {
        if (cancelled) return
        setCanAnswer(p.canAnswer)
        if (!p.canDetect) return
        return startCallDetection((s) => {
          setRinging(s === 'ringing')
          onCallState?.(s)
        })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [onCallState])

  const label: Record<BrainState, string> = {
    absent: 'brain: no native module',
    'not-loaded': 'brain: model not loaded',
    ready: 'brain: ready',
  }
  const dot: Record<BrainState, ViewStyle> = {
    absent: styles.dotOff,
    'not-loaded': styles.dotWarn,
    ready: styles.dotOn,
  }

  const onToggleCalls = useCallback(async () => {
    if (ringing) {
      const ok = await hangUp()
      setRinging(!ok)
    }
  }, [ringing])

  const onAnswer = useCallback(async () => {
    const ok = await answerCall()
    if (ok) setRinging(false)
  }, [])

  return (
    <View>
      {ringing ? (
        <View style={styles.ringBar}>
          <Text style={styles.ringText}>Incoming call</Text>
          <View style={styles.ringActions}>
            <TouchableOpacity
              style={[styles.ringBtn, styles.ringDecline]}
              onPress={onToggleCalls}
              activeOpacity={0.8}
            >
              <Text style={styles.ringBtnText}>Decline</Text>
            </TouchableOpacity>
            {canAnswer ? (
              <TouchableOpacity
                style={[styles.ringBtn, styles.ringAccept]}
                onPress={onAnswer}
                activeOpacity={0.8}
              >
                <Text style={styles.ringBtnText}>Answer</Text>
              </TouchableOpacity>
            ) : (
              // Answering needs a grant. Saying so beats a button that silently
              // does nothing.
              <Text style={styles.ringNeedsPerm}>answering needs permission</Text>
            )}
          </View>
        </View>
      ) : null}

      <TouchableOpacity
        style={styles.bar}
        onPress={() => setShowDetail((v) => !v)}
        activeOpacity={0.8}
      >
        <View style={[styles.dot, dot[state]]} />
        <Text style={styles.label}>{label[state]}</Text>
        {trace ? (
          <View style={styles.traceWrap}>
        <Text style={styles.trace}>
            {trace.source === 'router' ? 'routed' : 'heuristic'} ·{' '}
            {trace.route.replace('create_', '')} · m{trace.margin.toFixed(2)}
          </Text>
        </View>
        ) : null}
        <Text style={styles.chevron}>{showDetail ? '▾' : '▸'}</Text>
      </TouchableOpacity>

      {showDetail ? (
        <View style={styles.detail}>
          <Text style={styles.detailLine}>
            Router:{' '}
            {isLocalBrainAvailable
              ? 'native module present'
              : 'absent — heuristic only'}
          </Text>
          <Text style={styles.detailLine}>
            Routes: {Object.keys(ROUTE_PROTOTYPES).join(', ')}
          </Text>
          <Text style={styles.detailLine}>
            Calls:{' '}
            {isCallDetectionAvailable && isSupportedPlatform
              ? canAnswer
                ? 'detection + answering permitted'
                : 'detection only (answering not granted)'
              : 'unavailable on this platform'}
          </Text>
          {trace?.reason ? (
            <Text style={styles.detailLine}>{trace.reason}</Text>
          ) : null}
          <Text style={styles.detailNote}>
            A routing decision is only trustworthy if you can see how close it was.
            Margin is the gap to the best alternative; a thin margin means the
            router declined or fell back.
          </Text>
        </View>
      ) : null}
    </View>
  )
}

const makeStyles = (theme: ReturnType<typeof useTheme>) =>
  StyleSheet.create({
    bar: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.two,
      paddingHorizontal: Spacing.three,
      paddingVertical: Spacing.two,
    },
    dot: { width: 8, height: 8, borderRadius: 4 },
    dotOn: { backgroundColor: STATUS.ready },
    dotWarn: { backgroundColor: STATUS.warn },
    dotOff: { backgroundColor: STATUS.off },
    label: { color: theme.textSecondary, fontSize: 12 },
    traceWrap: { flex: 1 },
    trace: { color: theme.textSecondary, fontSize: 11 },
    chevron: { color: theme.textSecondary, fontSize: 12 },
    detail: {
      paddingHorizontal: Spacing.three,
      paddingBottom: Spacing.two,
      gap: Spacing.one,
    },
    detailLine: { color: theme.text, fontSize: 12 },
    detailNote: {
      color: theme.textSecondary,
      fontSize: 11,
      marginTop: Spacing.one,
      lineHeight: 15,
    },
    ringBar: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      backgroundColor: theme.backgroundElement,
      paddingHorizontal: Spacing.three,
      paddingVertical: 10,
    },
    ringText: { color: theme.text, fontSize: 14, fontWeight: '600' },
    ringActions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.two,
    },
    ringBtn: {
      paddingHorizontal: 14,
      paddingVertical: 7,
      borderRadius: 8,
    },
    ringAccept: { backgroundColor: STATUS.accept },
    ringDecline: { backgroundColor: STATUS.decline },
    ringBtnText: { color: STATUS.onAccent, fontSize: 13, fontWeight: '600' },
    ringNeedsPerm: { color: STATUS.warn, fontSize: 11 },
  });
