import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  AppState,
  FlatList,
  Image,
  NativeModules,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {desktopTokens as token} from './tokens';
import {ScrollFade, useScrollFade} from './ScrollFade';
import {createRewindTimeline} from './rewindTimeline';

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
  readFrame(
    id: string,
  ): Promise<{id: string; mimeType: 'image/jpeg'; base64: string}>;
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

export function DesktopRewind({
  captureRevision = 0,
  query = '',
}: {
  captureRevision?: number;
  query?: string;
}) {
  const fade = useScrollFade();
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
    setImage(null);
    setImageError(null);
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
          setImage(`data:image/jpeg;base64,${result.base64}`);
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
      {error !== null ? (
        <Text accessibilityRole="alert" style={styles.text}>
          {error}
        </Text>
      ) : null}
      <View style={styles.content}>
        <ScrollFade visible={fade.visible} style={styles.list}>
          <FlatList
            data={frames}
            keyExtractor={frame => frame.id}
            extraData={selected?.id}
            onLayout={fade.onLayout}
            onScroll={fade.onScroll}
            onContentSizeChange={fade.onContentSizeChange}
            scrollEventThrottle={16}
            contentContainerStyle={styles.rows}
            renderItem={({item: frame}) => (
              <FocusPressable
                key={frame.id}
                accessibilityRole="button"
                accessibilityLabel={`View capture ${frame.id}`}
                accessibilityState={{selected: selected?.id === frame.id}}
                onPress={() => setSelected(frame)}
                style={[
                  styles.row,
                  selected?.id === frame.id && styles.selected,
                ]}>
                <Text style={styles.text}>
                  {frame.appName || 'Captured screen'}
                </Text>
                <Text style={styles.meta} numberOfLines={2}>
                  {frame.windowTitle}
                </Text>
                <Text style={styles.meta}>
                  {new Date(frame.capturedAtMs).toLocaleString()}
                </Text>
              </FocusPressable>
            )}
            ListEmptyComponent={
              !busy && error === null ? (
                <Text style={styles.text}>
                  {query
                    ? 'No captures match this search.'
                    : 'No captures saved yet.'}
                </Text>
              ) : null
            }
            ListFooterComponent={
              <>
                {busy ? (
                  <Text style={styles.meta}>Loading screen history…</Text>
                ) : null}
                {hasMore ? (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel="Load more history"
                    disabled={busy}
                    onPress={() => void more()}
                    style={styles.button}>
                    <Text style={styles.text}>Load more</Text>
                  </FocusPressable>
                ) : null}
              </>
            }
          />
        </ScrollFade>
        <View style={styles.preview}>
          {selected === null ? (
            frames.length > 0 ? (
              <Text style={styles.meta}>Select a capture to view it.</Text>
            ) : null
          ) : imageError !== null ? (
            <Text accessibilityRole="alert" style={styles.text}>
              {imageError}
            </Text>
          ) : image === null ? (
            <Text style={styles.meta}>Loading captured frame…</Text>
          ) : (
            <Image
              key={selected.id}
              accessibilityLabel={`Captured screen from ${selected.appName}`}
              source={{uri: image}}
              resizeMode="contain"
              style={styles.image}
              onError={() => {
                setImage(null);
                setImageError('This captured frame could not be opened.');
              }}
            />
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, gap: 12, padding: 12},
  toolbar: {flexDirection: 'row', gap: 8, alignItems: 'center'},
  button: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: token.color.glassQuiet,
  },
  text: {color: token.color.ink, fontSize: 14},
  meta: {color: token.color.inkMuted, fontSize: 12},
  status: {flex: 1},
  content: {flex: 1, flexDirection: 'row', gap: 16},
  list: {width: 280, flexBasis: 280, flexGrow: 0, flexShrink: 1},
  rows: {gap: 8, paddingBottom: 12},
  row: {
    padding: 12,
    gap: 6,
    borderRadius: 12,
    backgroundColor: token.color.glassQuiet,
  },
  selected: {backgroundColor: token.color.glassSelected},
  preview: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 16,
    backgroundColor: 'transparent',
  },
  image: {width: '100%', height: '100%'},
});
