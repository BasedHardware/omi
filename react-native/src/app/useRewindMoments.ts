import {useCallback, useEffect, useRef, useState} from 'react';
import {AppState, NativeModules, Platform} from 'react-native';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from '../omiNative';
import {
  loadRewindMoments,
  recallFromMoment,
  upsertRewindMoment,
  type RewindMomentRecord,
} from '../rewindMomentsClient';
import {createRewindTimeline} from '../desktop/rewindTimeline';
import type {TimelineRecall} from '../timeline/mixedTimeline';

type Frame = {
  id: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
};

type Rewind = {
  listFrames(input: {
    source: 'shipping' | 'captured';
    query: string;
    cursor: string | null;
    limit: number;
  }): Promise<{frames: Frame[]; nextCursor: string | null}>;
};

export type RewindMomentsState = {
  items: TimelineRecall[];
  status: 'idle' | 'loading' | 'ready' | 'unavailable' | 'error';
  error: string | null;
  sync: 'idle' | 'saving' | 'saved' | 'unavailable' | 'error';
  syncError: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => void;
  refresh: () => void;
};

function localRecall(frame: Frame): TimelineRecall {
  const source = frame.id.startsWith('shipping:') ? 'shipping' : 'captured';
  return {
    kind: 'recall',
    id: frame.id,
    appName: frame.appName || 'Captured screen',
    windowTitle: frame.windowTitle,
    searchableText: `${frame.appName} ${frame.windowTitle}`,
    atMs: frame.capturedAtMs,
    source,
    local: true,
  };
}

function toMoment(frame: Frame): RewindMomentRecord | null {
  if (frame.id.length > 200) {
    return null;
  }
  const source = frame.id.startsWith('shipping:')
    ? 'shipping'
    : frame.id.startsWith('captured:')
    ? 'captured'
    : null;
  if (source === null) {
    return null;
  }
  return {
    frameId: frame.id,
    capturedAtMs: frame.capturedAtMs,
    appName: (frame.appName || 'Captured screen').slice(0, 256),
    windowTitle: frame.windowTitle.slice(0, 1024),
    source,
    ocrPreview: '',
  };
}

export function useRewindMoments(enabled: boolean): RewindMomentsState {
  const [items, setItems] = useState<TimelineRecall[]>([]);
  const [status, setStatus] = useState<RewindMomentsState['status']>('idle');
  const [error, setError] = useState<string | null>(null);
  const [sync, setSync] = useState<RewindMomentsState['sync']>('idle');
  const [syncError, setSyncError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const epoch = useRef(0);
  const paginated = useRef(false);
  const loading = useRef(false);
  const invalidated = useRef(false);
  const saved = useRef(new Set<string>());
  const nextPage = useRef<(() => void) | null>(null);
  const appState = useRef(AppState.currentState);
  const loadMore = useCallback(() => nextPage.current?.(), []);
  const refresh = useCallback(() => {
    if (!invalidated.current) setRevision(value => value + 1);
  }, []);

  const clear = useCallback(() => {
    epoch.current += 1;
    nextPage.current = null;
    loading.current = false;
    paginated.current = false;
    saved.current.clear();
    setItems([]);
    setStatus('idle');
    setError(null);
    setSync('idle');
    setSyncError(null);
    setHasMore(false);
    setLoadingMore(false);
  }, []);

  useEffect(
    () =>
      subscribeOmiBackendSessionInvalidated(() => {
        if (!enabled) return;
        invalidated.current = true;
        clear();
      }),
    [clear, enabled],
  );

  useEffect(() => {
    if (!enabled) {
      invalidated.current = false;
      clear();
      return;
    }
    if (invalidated.current) return;
    const current = (epoch.current += 1);
    const active = () => epoch.current === current;
    const retireOwner = (failure: unknown) => {
      const code = (failure as {code?: string} | null)?.code;
      if (code !== 'OMI_REWIND_AUTH' && code !== 'OMI_REWIND_OWNER_CHANGED')
        return false;
      invalidated.current = true;
      clear();
      setStatus('error');
      setError('Sign in again to open your screen history.');
      return true;
    };
    paginated.current = false;
    loading.current = false;
    setLoadingMore(false);
    setHasMore(false);
    setStatus(previous => (previous === 'ready' ? previous : 'loading'));
    setError(null);
    const native =
      Platform.OS === 'macos'
        ? (NativeModules.OmiRewind as Rewind | undefined)
        : undefined;
    const backend = omiBackend;
    const timeline = native ? createRewindTimeline(native, '') : null;
    let localMore = timeline !== null;
    let remoteMore = backend != null;
    let cursor: string | null = null;
    const load = async (append: boolean) => {
      if (!active() || loading.current) return;
      loading.current = true;
      if (append) {
        paginated.current = true;
        setLoadingMore(true);
      }
      const local: TimelineRecall[] = [];
      let localError: string | null = null;
      if (timeline !== null && localMore) {
        try {
          const page = await timeline.next();
          if (!active()) return;
          local.push(...page.frames.map(localRecall));
          localMore = page.next;
          if (page.warning) {
            localError = page.warning;
          }
        } catch (failure) {
          if (!active()) return;
          localMore = false;
          if (retireOwner(failure)) return;
          const code = (failure as {code?: string} | null)?.code;
          localError =
            code === 'OMI_REWIND_UNAVAILABLE'
              ? 'No local Recall history is available on this device.'
              : 'Screen history could not be loaded.';
        }
      } else if (timeline === null && Platform.OS === 'macos') {
        localError = 'No local Recall history is available on this device.';
      }

      let remote: TimelineRecall[] = [];
      let remoteError: string | null = null;
      const remoteRecords = new Map<string, RewindMomentRecord>();
      if (backend === undefined || backend === null) {
        remoteError =
          'Recall cannot save until this app has a signed-in backend.';
        if (active()) {
          setSync('unavailable');
          setSyncError(remoteError);
        }
      } else if (remoteMore) {
        try {
          const page = await loadRewindMoments(backend, cursor);
          if (!active()) return;
          remote = page.items.map(recallFromMoment);
          for (const moment of page.items)
            remoteRecords.set(moment.frameId, moment);
          cursor = page.nextCursor;
          remoteMore = page.hasMore;
        } catch (failure) {
          if (!active() || retireOwner(failure)) return;
          remoteError = 'Saved Recall metadata could not be loaded.';
        }
      }

      if (!active()) return;
      setItems(previous => {
        const merged = new Map(
          (append ? previous : []).map(item => [item.id, item]),
        );
        for (const item of remote) {
          if (!merged.get(item.id)?.local) merged.set(item.id, item);
        }
        for (const item of local) merged.set(item.id, item);
        return [...merged.values()].sort(
          (a, b) => (b.atMs ?? 0) - (a.atMs ?? 0),
        );
      });
      setHasMore(localMore || remoteMore);
      if (
        !append &&
        local.length === 0 &&
        remote.length === 0 &&
        (localError || remoteError)
      ) {
        setStatus('error');
        setError(localError ?? remoteError);
      } else {
        setStatus('ready');
        setError(localError ?? remoteError);
      }

      if (backend && local.length > 0) {
        setSync('saving');
        let failed = 0;
        for (const frame of local) {
          if (!active()) return;
          const moment = toMoment({
            id: frame.id,
            capturedAtMs: frame.atMs ?? 0,
            appName: frame.appName,
            windowTitle: frame.windowTitle,
          });
          if (moment === null) {
            continue;
          }
          const key = JSON.stringify(moment);
          if (
            saved.current.has(key) ||
            key === JSON.stringify(remoteRecords.get(moment.frameId))
          )
            continue;
          try {
            await upsertRewindMoment(backend, moment);
            if (!active()) return;
            saved.current.add(key);
          } catch (failure) {
            if (!active() || retireOwner(failure)) return;
            failed += 1;
          }
        }
        if (!active()) return;
        if (failed > 0) {
          setSync('error');
          setSyncError(
            'Some screen history stayed on this device and was not saved to your account.',
          );
        } else {
          setSync('saved');
          setSyncError(null);
        }
      } else if (backend && local.length === 0 && Platform.OS !== 'macos') {
        setSync(remoteError ? 'error' : 'idle');
      }
    };
    const run = (append: boolean) =>
      load(append)
        .catch(() => {
          if (active()) {
            setStatus('error');
            setError('Screen history could not be loaded.');
          }
        })
        .finally(() => {
          if (active()) {
            loading.current = false;
            setLoadingMore(false);
          }
        });
    nextPage.current = () => {
      if (active() && !loading.current && (localMore || remoteMore))
        void run(true);
    };
    void run(false);
    return () => {
      epoch.current += 1;
      nextPage.current = null;
    };
  }, [enabled, revision, clear]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const tick = () => {
      if (
        !loading.current &&
        !paginated.current &&
        !invalidated.current &&
        appState.current === 'active'
      ) {
        setRevision(value => value + 1);
      }
    };
    const listener = AppState.addEventListener('change', state => {
      appState.current = state;
      if (state === 'active') {
        tick();
      }
    });
    const timer = setInterval(tick, 15000);
    return () => {
      clearInterval(timer);
      listener.remove();
    };
  }, [enabled]);

  return {
    items,
    status,
    error,
    sync,
    syncError,
    refresh,
    hasMore,
    loadingMore,
    loadMore,
  };
}
