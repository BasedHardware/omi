import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  AppState,
  NativeModules,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {MaterialIcon} from '../ui/MaterialIcon';

import {DesktopEmptyState} from './DesktopRows';
import {RewindFrameView} from './RewindFrameView';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';
import {createRewindTimeline, groupRewindFrames} from './rewindTimeline';

type Frame = {
  id: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};
type Page = {frames: Frame[]; nextCursor: string | null};
type Rewind = {
  listFrames(input: {
    source: 'shipping' | 'captured';
    query: string;
    cursor: string | null;
    limit: number;
  }): Promise<Page>;
  readFrame(id: string): Promise<{
    id: string;
    mimeType: 'image/jpeg';
    base64: string;
  }>;
};

function errorCopy(error: unknown) {
  const code = (error as {code?: string} | null)?.code;
  if (code === 'OMI_REWIND_UNAVAILABLE') {
    return 'No local Recall history is available for this account on this Mac.';
  }
  if (code === 'OMI_REWIND_AUTH' || code === 'OMI_REWIND_OWNER_CHANGED') {
    return 'Sign in again from Settings to open your screen history.';
  }
  return 'Screen history could not be loaded.';
}

function dayLabel(atMs: number) {
  const day = new Date(atMs);
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const deltaDays = Math.round(
    (startOfToday.getTime() - new Date(atMs).setHours(0, 0, 0, 0)) / 86400000,
  );
  if (deltaDays <= 0) {
    return 'Today';
  }
  if (deltaDays === 1) {
    return 'Yesterday';
  }
  return day.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });
}

function timeLabel(atMs: number) {
  return new Date(atMs).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function DesktopRewind({
  captureRevision = 0,
  query = '',
  focusCaptureId = null,
}: {
  captureRevision?: number;
  query?: string;
  /** Frame id to open directly, e.g. from an Activity timeline entry. */
  focusCaptureId?: string | null;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const seenRevision = useRef(captureRevision);
  const lastQuery = useRef(query);
  const paginated = useRef(false);
  const appState = useRef(AppState.currentState);
  const [revision, setRevision] = useState(0);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const timeline = useRef<ReturnType<typeof createRewindTimeline> | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Frame | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const epoch = useRef(0);
  const imageEpoch = useRef(0);
  const loading = useRef(false);
  const bridge = NativeModules.OmiRewind as Rewind | undefined;
  const handleFailure = useCallback((failure: unknown) => {
    const code = (failure as {code?: string} | null)?.code;
    if (code === 'OMI_REWIND_AUTH' || code === 'OMI_REWIND_OWNER_CHANGED') {
      epoch.current += 1;
      imageEpoch.current += 1;
      timeline.current = null;
      loading.current = false;
      // The list is cleared, so a prior "load more" must not keep the
      // automatic refresh disabled forever: without this, Recall stays frozen
      // on the auth error after the session returns.
      paginated.current = false;
      setBusy(false);
      setFrames([]);
      setHasMore(false);
      setSelected(null);
      setImage(null);
      setImageError(null);
    }
    setError(errorCopy(failure));
  }, []);

  useEffect(() => {
    const current = (epoch.current += 1);
    if (lastQuery.current !== query) {
      setFrames([]);
      setHasMore(false);
      setSelected(null);
      lastQuery.current = query;
      paginated.current = false;
    }
    setError(null);
    setBusy(true);
    loading.current = true;
    const reader =
      bridge === undefined ? null : createRewindTimeline(bridge, query);
    timeline.current = reader;
    const request =
      reader === null
        ? Promise.reject({code: 'OMI_REWIND_UNAVAILABLE'})
        : reader.next();
    request
      .then(
        page => {
          if (epoch.current !== current) {
            return;
          }
          setFrames(page.frames);
          setHasMore(page.next);
          setError(page.warning ?? null);
        },
        failure => {
          if (epoch.current === current) {
            handleFailure(failure);
          }
        },
      )
      .finally(() => {
        if (epoch.current === current) {
          setBusy(false);
          loading.current = false;
        }
      });
    return () => {
      epoch.current += 1;
    };
  }, [bridge, query, revision, handleFailure]);

  useEffect(() => {
    if (
      !busy &&
      !paginated.current &&
      appState.current === 'active' &&
      seenRevision.current !== captureRevision
    ) {
      seenRevision.current = captureRevision;
      setRevision(value => value + 1);
    }
  }, [busy, captureRevision]);

  // Opening a capture from the Activity timeline: select its frame as soon as
  // the first page that contains it has loaded.
  const seenFocus = useRef<string | null>(null);
  useEffect(() => {
    if (focusCaptureId === null || busy) {
      return;
    }
    if (seenFocus.current === focusCaptureId) {
      return;
    }
    const frame = frames.find(item => item.id === focusCaptureId);
    if (frame === undefined) {
      return;
    }
    seenFocus.current = focusCaptureId;
    setSelected(frame);
  }, [busy, focusCaptureId, frames]);
  useEffect(() => {
    const refresh = () => {
      if (
        !loading.current &&
        !paginated.current &&
        appState.current === 'active'
      ) {
        setRevision(value => value + 1);
      }
    };
    const listener = AppState.addEventListener('change', state => {
      appState.current = state;
      if (state === 'active') {
        refresh();
      }
    });
    const timer = setInterval(refresh, 15000);
    return () => {
      clearInterval(timer);
      listener.remove();
    };
  }, []);

  useEffect(() => {
    let active = true;
    const currentImage = ++imageEpoch.current;
    setImageError(null);
    // Keep the previous frame on screen while the next one loads: swapping
    // through null remounts the Image and cancels loads mid-flight, which
    // trips a react-native-macOS request-token assert in dev.
    if (selected !== null && bridge !== undefined) {
      bridge.readFrame(selected.id).then(
        result => {
          if (!active || imageEpoch.current !== currentImage) {
            return;
          }
          if (
            result.id !== selected.id ||
            result.mimeType !== 'image/jpeg' ||
            !result.base64
          ) {
            setImageError('This captured frame could not be opened.');
            return;
          }
          // The base64 payload renders through the native RewindFrameView:
          // URI-based <Image> loads go through RCTNetworking on
          // react-native-macOS, whose data:/file: handlers pass a nil
          // request token (upstream bug) and fatal dev builds with
          // "Unrecognized request token".
          setImage(result.base64);
        },
        failure => {
          if (active && imageEpoch.current === currentImage) {
            const code = (failure as {code?: string} | null)?.code;
            if (
              code === 'OMI_REWIND_AUTH' ||
              code === 'OMI_REWIND_OWNER_CHANGED'
            ) {
              handleFailure(failure);
              return;
            }
            setImageError('This captured frame could not be opened.');
          }
        },
      );
    }
    return () => {
      active = false;
    };
  }, [bridge, selected, handleFailure]);

  const more = async () => {
    if (loading.current || !hasMore || timeline.current === null) {
      return;
    }
    const current = epoch.current;
    paginated.current = true;
    loading.current = true;
    setBusy(true);
    setError(null);
    try {
      const page = await timeline.current.next();
      if (epoch.current !== current) {
        return;
      }
      setFrames(previous => {
        const ids = new Set(previous.map(frame => frame.id));
        return [
          ...previous,
          ...page.frames.filter(frame => !ids.has(frame.id)),
        ];
      });
      setHasMore(page.next);
      setError(page.warning ?? null);
    } catch (failure) {
      if (epoch.current === current) {
        handleFailure(failure);
      }
    } finally {
      if (epoch.current === current) {
        loading.current = false;
        setBusy(false);
      }
    }
  };
  return (
    <View style={styles.root} accessibilityLabel="Recall screen history">
      {error !== null && frames.length > 0 ? (
        <Text accessibilityRole="alert" style={styles.text}>
          {error}
        </Text>
      ) : null}
      {frames.length === 0 ? (
        <DesktopEmptyState
          icon="monitor"
          error={!busy && error !== null}
          title={
            busy
              ? 'Finding your moments…'
              : error
              ? 'Screen history is unavailable'
              : query
              ? 'Nothing matches yet'
              : 'A place for what you saw.'
          }
          detail={
            busy
              ? 'Loading screen history…'
              : error ??
                (query
                  ? 'No captures match this search.'
                  : 'No captures saved yet.')
          }
        />
      ) : (
        <View style={styles.content}>
          <View style={styles.list}>
            <ScrollView
              scrollEventThrottle={16}
              contentContainerStyle={styles.rows}>
              {(() => {
                let lastDay = '';
                return groupRewindFrames(frames).map(group => {
                  const day = dayLabel(group.capturedAtMs);
                  const showDay = day !== lastDay;
                  lastDay = day;
                  const isSelected = selected?.id === group.id;
                  const title =
                    group.windowTitle || group.appName || 'Captured screen';
                  const meta =
                    group.windowTitle && group.windowTitle !== group.appName
                      ? `${group.appName} · ${group.count} capture${
                          group.count === 1 ? '' : 's'
                        }`
                      : `${group.count} capture${group.count === 1 ? '' : 's'}`;
                  return (
                    <View key={group.id}>
                      {showDay ? <Text style={styles.day}>{day}</Text> : null}
                      <FocusPressable
                        accessibilityRole="button"
                        accessibilityLabel={`View capture ${group.id}`}
                        accessibilityState={{selected: isSelected}}
                        onPress={() => setSelected(group.frame)}
                        style={[styles.row, isSelected && styles.selected]}>
                        <Text style={styles.time}>
                          {timeLabel(group.capturedAtMs)}
                        </Text>
                        <View style={styles.dotColumn}>
                          <View
                            style={[styles.dot, isSelected && styles.dotOn]}
                          />
                        </View>
                        <View style={styles.rowBody}>
                          <Text style={styles.text} numberOfLines={1}>
                            {title}
                          </Text>
                          <Text style={styles.meta} numberOfLines={2}>
                            {meta}
                          </Text>
                        </View>
                      </FocusPressable>
                    </View>
                  );
                });
              })()}
              {busy ? (
                <Text style={styles.meta}>Loading screen history…</Text>
              ) : hasMore ? (
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel="Load more history"
                  disabled={busy}
                  onPress={() => void more()}
                  style={styles.more}>
                  <Text style={styles.moreText}>Load more</Text>
                </FocusPressable>
              ) : null}
            </ScrollView>
          </View>
          <View style={styles.preview}>
            {selected === null ? (
              <View style={styles.previewPrompt}>
                <MaterialIcon
                  name="monitor"
                  size={32}
                  color={token.color.inkFaint}
                />
                <Text style={styles.meta}>Select a capture to view it.</Text>
              </View>
            ) : imageError !== null ? (
              <Text accessibilityRole="alert" style={styles.text}>
                {imageError}
              </Text>
            ) : image === null ? (
              <Text style={styles.meta}>Loading captured frame…</Text>
            ) : (
              <RewindFrameView
                key={selected.id}
                accessibilityLabel={`Captured screen from ${selected.appName}`}
                imageBase64={image}
                style={styles.image}
              />
            )}
          </View>
        </View>
      )}
    </View>
  );
}

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    root: {flex: 1, paddingHorizontal: 24, paddingTop: 16, paddingBottom: 12},
    text: {color: token.color.ink, fontSize: 14, lineHeight: 21},
    meta: {color: token.color.inkMuted, fontSize: 12, lineHeight: 19},
    content: {flex: 1, flexDirection: 'row', gap: 20},
    list: {width: 300, flexBasis: 300, flexGrow: 0, flexShrink: 1},
    rows: {gap: 2, paddingBottom: 24},
    day: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 12,
      fontWeight: '600',
      letterSpacing: 0.4,
      textTransform: 'uppercase',
      marginTop: 16,
      marginBottom: 6,
      marginLeft: 60,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
      paddingVertical: 8,
      paddingRight: 8,
      borderRadius: 12,
    },
    selected: {backgroundColor: token.color.glassSelected},
    time: {
      color: token.color.inkFaint,
      fontSize: 11,
      lineHeight: 21,
      width: 44,
      textAlign: 'right',
    },
    dotColumn: {width: 14, alignItems: 'center', paddingTop: 7},
    dot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: token.color.inkFaint,
      opacity: 0.7,
    },
    dotOn: {backgroundColor: token.color.ink, opacity: 1},
    rowBody: {flex: 1, minWidth: 0},
    more: {
      alignSelf: 'flex-start',
      marginLeft: 60,
      marginTop: 10,
      paddingVertical: 8,
      paddingHorizontal: 14,
      borderRadius: 10,
      backgroundColor: token.color.glassQuiet,
    },
    moreText: {color: token.color.inkMuted, fontSize: 12},
    preview: {
      flex: 1,
      minWidth: 0,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 16,
      backgroundColor: token.color.glassQuiet,
      borderWidth: 1,
      borderColor: token.color.line,
      overflow: 'hidden',
    },
    previewPrompt: {alignItems: 'center', gap: 16, padding: 24},
    image: {width: '100%', height: '100%'},
  });
