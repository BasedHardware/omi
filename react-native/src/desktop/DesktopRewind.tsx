import React, {useEffect, useRef, useState} from 'react';
import {
  Image,
  NativeModules,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {desktopTokens as token} from './tokens';
import type {useRewindCapture} from '../app/useRewindCapture';

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

function errorCode(error: unknown): string | undefined {
  return (error as {code?: string} | null)?.code;
}

function errorCopy(error: unknown) {
  const code = errorCode(error);
  if (code === 'OMI_REWIND_UNAVAILABLE')
    return 'No local Rewind history is available for this account on this Mac.';
  if (code === 'OMI_REWIND_AUTH')
    return 'Sign in again to open your screen history.';
  return 'Screen history could not be loaded. Try again.';
}

export function rewindLaterPageCanRetry(error: unknown): boolean {
  const code = errorCode(error);
  return code !== 'OMI_REWIND_UNAVAILABLE' && code !== 'OMI_REWIND_AUTH';
}

export function DesktopRewind({
  capture,
  captureRevision = 0,
}: {
  capture?: ReturnType<typeof useRewindCapture>;
  captureRevision?: number;
}) {
  const capturedRevision = useRef(captureRevision);
  capturedRevision.current = captureRevision;
  const [seenRevision, setSeenRevision] = useState(captureRevision);
  const [source, setSource] = useState<'shipping' | 'captured'>('shipping');
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [revision, setRevision] = useState(0);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Frame | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const epoch = useRef(0);
  const loading = useRef(false);
  const bridge = NativeModules.OmiRewind as Rewind | undefined;

  useEffect(() => {
    const current = (epoch.current += 1);
    setFrames([]);
    setCursor(null);
    setSelected(null);
    setError(null);
    setSeenRevision(capturedRevision.current);
    setBusy(true);
    loading.current = true;
    const request =
      bridge === undefined
        ? Promise.reject({code: 'OMI_REWIND_UNAVAILABLE'})
        : bridge.listFrames({source, query, cursor: null, limit: 50});
    request
      .then(
        page => {
          if (epoch.current !== current) return;
          setFrames(page.frames);
          setCursor(page.nextCursor);
        },
        failure => {
          if (epoch.current === current) setError(errorCopy(failure));
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
  }, [bridge, source, query, revision]);

  useEffect(() => {
    let active = true;
    setImage(null);
    setImageError(null);
    if (selected !== null && bridge !== undefined) {
      bridge.readFrame(selected.id).then(
        result => {
          if (!active) return;
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
        () => {
          if (active) setImageError('This captured frame could not be opened.');
        },
      );
    }
    return () => {
      active = false;
    };
  }, [bridge, selected]);

  const more = async () => {
    if (loading.current || cursor === null || bridge === undefined) return;
    const current = epoch.current;
    loading.current = true;
    setBusy(true);
    setError(null);
    try {
      const page = await bridge.listFrames({source, query, cursor, limit: 50});
      if (epoch.current !== current) return;
      setFrames(previous => {
        const ids = new Set(previous.map(frame => frame.id));
        return [
          ...previous,
          ...page.frames.filter(frame => !ids.has(frame.id)),
        ];
      });
      setCursor(page.nextCursor);
    } catch (failure) {
      if (epoch.current === current) {
        setError(errorCopy(failure));
        if (!rewindLaterPageCanRetry(failure)) {
          setCursor(null);
        }
      }
    } finally {
      if (epoch.current === current) {
        loading.current = false;
        setBusy(false);
      }
    }
  };
  const search = () => {
    setQuery(draft.trim());
    setRevision(value => value + 1);
  };
  return (
    <View style={styles.root} accessibilityLabel="Rewind screen history">
      <View style={styles.toolbar}>
        <TextInput
          accessibilityLabel="Search screen history"
          placeholder="Search screen history"
          maxLength={200}
          value={draft}
          onChangeText={setDraft}
          onSubmitEditing={search}
          style={styles.input}
        />
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Search history"
          onPress={search}
          style={styles.button}>
          <Text style={styles.text}>Search</Text>
        </FocusPressable>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Refresh history"
          onPress={() => setRevision(value => value + 1)}
          style={styles.button}>
          <Text style={styles.text}>Refresh</Text>
        </FocusPressable>
      </View>
      <View style={styles.toolbar}>
        {(['shipping', 'captured'] as const).map(value => (
          <FocusPressable
            key={value}
            accessibilityRole="button"
            accessibilityState={{selected: source === value}}
            onPress={() => setSource(value)}
            style={[styles.button, source === value && styles.selected]}>
            <Text style={styles.text}>
              {value === 'shipping' ? 'Existing Omi history' : 'This app'}
            </Text>
          </FocusPressable>
        ))}
      </View>
      <Text style={styles.meta}>
        Screen history stored on this Mac. Search matches captured text, apps,
        and window titles.
      </Text>
      {capture !== undefined ? (
        <View style={styles.toolbar}>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel={
              capture.capturing || capture.busy
                ? 'Stop screen capture'
                : 'Start screen capture'
            }
            disabled={!capture.available}
            onPress={() => {
              if (capture.capturing || capture.busy)
                void capture.stop().catch(() => undefined);
              else {
                setSource('captured');
                void capture.start();
              }
            }}
            style={styles.button}>
            <Text style={styles.text}>
              {capture.capturing || capture.busy
                ? 'Stop capture'
                : 'Start capture'}
            </Text>
          </FocusPressable>
          <Text style={[styles.meta, styles.status]}>
            {!capture.available
              ? 'Capture is available in the native Mac app.'
              : capture.capturing
              ? 'Capturing the active window. Password managers and excluded apps are skipped.'
              : capture.busy
              ? 'Waiting for screen recording permission…'
              : 'Capture is stopped. Start to save new screen history.'}
          </Text>
        </View>
      ) : null}
      {capture?.error ? (
        <Text accessibilityRole="alert" style={styles.text}>
          {capture.error}
        </Text>
      ) : null}
      {source === 'captured' && captureRevision > seenRevision ? (
        <Text style={styles.meta}>
          New captures are saved. Refresh to view them.
        </Text>
      ) : null}
      {error !== null ? (
        <Text accessibilityRole="alert" style={styles.text}>
          {error}
        </Text>
      ) : null}
      <View style={styles.content}>
        <ScrollView style={styles.list} contentContainerStyle={styles.rows}>
          {frames.map(frame => (
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
          ))}
          {busy ? (
            <Text style={styles.meta}>Loading screen history…</Text>
          ) : null}
          {!busy && error === null && frames.length === 0 && cursor === null ? (
            <Text style={styles.text}>
              {query
                ? 'No captures match this search.'
                : 'No captures saved yet.'}
            </Text>
          ) : null}
          {cursor !== null ? (
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Load more history"
              disabled={busy}
              onPress={() => void more()}
              style={styles.button}>
              <Text style={styles.text}>Load more</Text>
            </FocusPressable>
          ) : null}
        </ScrollView>
        <View style={styles.preview}>
          {selected === null ? (
            <Text style={styles.meta}>Select a capture to view it.</Text>
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
  input: {
    flex: 1,
    minWidth: 0,
    borderRadius: 12,
    backgroundColor: token.color.glassQuiet,
    padding: 12,
    color: token.color.ink,
  },
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
    backgroundColor: token.color.glassQuiet,
  },
  image: {width: '100%', height: '100%'},
});
